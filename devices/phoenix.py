import struct
import time
from dataclasses import dataclass
from enum import Enum
import math
from typing import Optional

import serial
from serial import SerialException


class PhoenixState(Enum):
    INVERTING = 2
    DEVICE_ON = 3
    DEVICE_OFF = 4
    ECO_MODE = 5
    HIBERNATE = 253


class VEDirectCommand(Enum):
    ENTER_BOOT = 0
    PING = 1
    APP_VERSION = 3
    PRODUCT_ID = 4
    RESTART = 6
    GET = 7
    SET = 8
    ASYNC = "A"

    def to_bytes(self) -> bytes:
        return self.value.to_bytes(1, byteorder="little")


class VEDirectFlag(Enum):
    OK = 0
    NOT_FOUND = 1
    READ_ONLY = 2
    PARAMETER_ERROR = 3
    UNKNOWN = 4

    def to_bytes(self) -> bytes:
        return self.value.to_bytes(1, byteorder="little")


@dataclass
class VEDirectRequest:
    cmd: VEDirectCommand
    register: str
    flag: VEDirectFlag
    value: Optional[int] = None

    @staticmethod
    def _checksum(p0: bytes) -> bytes:
        return ((85 - sum(p0)) & 0xFF).to_bytes(1, byteorder="little")

    @staticmethod
    def _int_to_min_bytes(i: int) -> bytes:
        return i.to_bytes(math.ceil(i.bit_length() / 8), byteorder="little")

    def to_bytes(self) -> bytes:
        register_bytes = int(self.register, 16).to_bytes(2, byteorder="little")
        value_bytes = self._int_to_min_bytes(self.value) if self.value is not None else b""
        request_bytes = self.cmd.to_bytes() + register_bytes + self.flag.to_bytes() + value_bytes
        checksum = self._checksum(request_bytes)
        return request_bytes + checksum

    def to_hex(self) -> bytes:
        return self.to_bytes().hex()[1:].upper().encode()


@dataclass
class VEDirectResponse:
    cmd: VEDirectCommand
    register: str
    flag: VEDirectFlag
    value: Optional[int] = None

    @staticmethod
    def _checksum(p0: bytes) -> bool:
        return (85 - sum(p0)) & 0xFF == 0

    @classmethod
    def from_bytes(cls, p0: bytes):
        cmd = p0[0]
        register = struct.unpack("<H", p0[1:3])[0]
        flag = p0[3]
        value = p0[4:-1]

        if len(value) == 1:
            fmt = "B"
        elif len(value) == 2:
            fmt = "<H"
        elif len(value) == 4:
            fmt = "<L"
        elif len(value) == 8:
            fmt = "<Q"
        else:
            fmt = None

        if fmt is not None:
            value = struct.unpack(fmt, p0[4:-1])[0]
        else:
            value = None

        if not cls._checksum(p0):
            raise ValueError(f"Checksum failed generating VEDirectResponse({p0})")

        return cls(
            cmd=VEDirectCommand(cmd),
            register=f"0x{register:04X}",
            flag=VEDirectFlag(flag),
            value=value,
        )

    def check(self, request: VEDirectRequest):
        if self.cmd != request.cmd:
            raise ValueError(f"Command mismatch: {self.cmd} != {request.cmd}")

        if self.register != request.register:
            raise ValueError(f"Register mismatch: {self.register} != {request.register}")

        if self.flag != VEDirectFlag.OK:
            raise ValueError(f"Return flag was: {self.flag}")

        if request.value is not None and self.value != request.value:
            raise ValueError(f"Value mismatch: {self.value} != {request.value}")


class PhoenixInverter:
    BAUD = 19200

    _serial: Optional[serial.Serial] = None
    _telemetry: dict = {}
    _tty: str = None

    def __init__(self, tty):
        self._tty = tty.removeprefix("/dev/")
        self.connect()

    @staticmethod
    def _checksum(p0: bytes) -> bool:
        return sum(p0) % 256 == 0

    def execute(self, request: VEDirectRequest) -> VEDirectResponse:
        # Clear out the buffers
        self._serial.reset_input_buffer()
        self._serial.reset_output_buffer()

        # Send the command
        self._serial.write(b":" + request.to_hex() + b"\n")

        # Read and discard anything until the response begins
        _ = self._serial.read_until(b":")

        # The response is between :{response}\n
        resp = self._serial.read_until(b"\n").strip()
        resp_bytes = bytes.fromhex(f"0{resp.decode()}")

        return VEDirectResponse.from_bytes(resp_bytes)

    def connect(self) -> None:
        try:
            self._serial = serial.Serial(
                f"/dev/{self._tty}", baudrate=self.BAUD, timeout=0.25, write_timeout=0.5
            )
        except SerialException as exc:
            self._serial = None

            raise exc

    def disconnect(self) -> None:
        if self._serial is not None:
            self._serial.close()

        self._serial = None

    def read_telemetry_frame(self):
        self._serial.reset_output_buffer()

        raw = b""
        telemetry = {}

        while True:
            raw_line = self._serial.read_until(b"\r\n")
            line = raw_line.strip().decode("ascii", "ignore")

            if line == "" or not "\t" in line:
                continue

            key, value = line.split("\t")
            telemetry[key] = value
            raw += raw_line

            if key == "Checksum":
                if not raw.endswith(b"\r\n"):
                    raw += b"\r\n"

                if len(telemetry) == 12 and self._checksum(raw):
                    break
                else:
                    raw = b""
                    telemetry = {}

        self._telemetry = telemetry

    @property
    def ac_current(self) -> float:
        try:
            return round(float(self._telemetry["AC_OUT_I"]) / 1000.0, 2)
        except KeyError:
            return 0.0

    @property
    def dc_voltage(self) -> float:
        try:
            return float(self._telemetry["V"]) / 1000.0
        except KeyError:
            return 0.0

    @property
    def low_voltage_alarm(self) -> Optional[float]:
        req = VEDirectRequest(
            cmd=VEDirectCommand.GET,
            register="0x0320",
            flag=VEDirectFlag.OK,
        )

        resp = self.execute(req)
        resp.check(req)

        return resp.value / 100.0

    @low_voltage_alarm.setter
    def low_voltage_alarm(self, value: float):
        req = VEDirectRequest(
            cmd=VEDirectCommand.SET,
            register="0x0320",
            flag=VEDirectFlag.OK,
            value=int(round(value * 100.0)),
        )

        resp = self.execute(req)
        resp.check(req)

    @property
    def low_voltage_clear(self) -> Optional[float]:
        req = VEDirectRequest(
            cmd=VEDirectCommand.GET,
            register="0x0321",
            flag=VEDirectFlag.OK,
        )

        resp = self.execute(req)
        resp.check(req)

        return resp.value / 100.0

    @low_voltage_clear.setter
    def low_voltage_clear(self, value: float):
        req = VEDirectRequest(
            cmd=VEDirectCommand.SET,
            register="0x0321",
            flag=VEDirectFlag.OK,
            value=int(round(value * 100.0)),
        )

        resp = self.execute(req)
        resp.check(req)

    @property
    def shutdown_voltage(self) -> Optional[float]:
        req = VEDirectRequest(
            cmd=VEDirectCommand.GET,
            register="0x2210",
            flag=VEDirectFlag.OK,
        )

        resp = self.execute(req)
        resp.check(req)

        return resp.value / 100.0

    @shutdown_voltage.setter
    def shutdown_voltage(self, value: float):
        req = VEDirectRequest(
            cmd=VEDirectCommand.SET,
            register="0x2210",
            flag=VEDirectFlag.OK,
            value=int(round(value * 100.0)),
        )

        resp = self.execute(req)
        resp.check(req)

    @property
    def state(self) -> Optional[PhoenixState]:
        try:
            return PhoenixState(int(self._telemetry["MODE"]))
        except KeyError:
            return None

    def on(self):
        print(f"[phoenix] turning on")

        req = VEDirectRequest(
            cmd=VEDirectCommand.SET,
            register="0x0200",
            flag=VEDirectFlag.OK,
            value=2,
        )
        resp = self.execute(req)
        resp.check(req)

    def off(self):
        print(f"[phoenix] turning off")

        req = VEDirectRequest(
            cmd=VEDirectCommand.SET,
            register="0x0200",
            flag=VEDirectFlag.OK,
            value=4,
        )
        resp = self.execute(req)
        resp.check(req)


if __name__ == "__main__":
    foo = PhoenixInverter("/dev/ttyS5")

    while True:
        foo.read_telemetry_frame()
        print(f"ac_curr_out: {foo.ac_current} dc_volt_in: {foo.dc_voltage} state: {foo.state}")
        time.sleep(1)
