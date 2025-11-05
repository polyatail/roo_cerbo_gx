#!/usr/bin/env python3
import os
import time
from typing import Optional

import dbus
import serial
from dbus.mainloop.glib import DBusGMainLoop
from gi.repository import GLib
from serial.serialutil import SerialException

from lib.vedbus import VeDbusService


class VanOBDConnection:
    BAUD = 115200
    ELM_INIT = [
        ("ATE0", True),
        ("ATL0", False),
        ("ATS0", False),
        ("ATH0", False),
        ("ATSP0", False),
    ]
    POSSIBLE_PORTS = ["/dev/ttyUSB0", "/dev/ttyUSB1", "/dev/ttyUSB2"]

    port: Optional[str] = None
    _serial: Optional[serial.Serial] = None

    @staticmethod
    def _encode(cmd: str) -> bytes:
        return cmd.encode("ascii", "ignore")

    @staticmethod
    def _decode(resp: bytes) -> str:
        return resp.decode("ascii", "ignore")

    @staticmethod
    def _split_hex(resp: str) -> list[str]:
        return [resp[i : i + 2] for i in range(0, len(resp), 2)]

    def connect(self, port: str) -> None:
        try:
            self._serial = serial.Serial(port, baudrate=self.BAUD, timeout=0.25, write_timeout=0.5)
            self.port = port
        except SerialException as exc:
            self._serial = None
            self.port = None

            raise exc

    def elm_init(self):
        self.reset()

        for cmd, echo in self.ELM_INIT:
            resp = self.execute(cmd, echo)

            if resp != "OK":
                raise IOError(f"invalid response to {cmd}: {resp}")

            print(f"[obd] init: {cmd} resp: {resp}")

        banner = self.execute("ATI")

        if not banner.startswith("ELM327"):
            raise IOError(f"unrecognized device: {banner}")

        print(f"[obd] banner: {banner}")

    def disconnect(self):
        if self._serial is not None:
            self._serial.close()

        self._serial = None
        self.port = None

    def reset(self):
        if self._serial is None:
            raise IOError("can not call reset without first calling connect")

        self._serial.reset_input_buffer()
        self._serial.reset_output_buffer()
        self._serial.write(self._encode(f"ATZ\r"))

        time.sleep(2)

        self._serial.reset_input_buffer()
        self._serial.reset_output_buffer()

    def execute(self, cmd: str, echo: bool = False) -> str:
        if self._serial is None:
            raise IOError("can not call execute without first calling connect")

        self._serial.reset_input_buffer()
        self._serial.reset_output_buffer()
        self._serial.write(self._encode(f"{cmd}\r"))

        time.sleep(0.2)

        if echo:
            echoed_cmd = self._decode(self._serial.read_until(b"\r").rstrip())

            if echoed_cmd != cmd:
                raise IOError(f"expected echo, got: {echoed_cmd}")

        return self._decode(self._serial.read_until(b"\r").rstrip())

    def detect_adapter(self) -> None:
        print("[obd] scanning for adapter...")

        for port in self.POSSIBLE_PORTS:
            try:
                print(f"[obd] trying port {port}...")

                if not os.path.exists(port):
                    raise IOError("no device connected on this port")

                self.connect(port)
                self.elm_init()
            except Exception as exc:
                print(f"[obd] port {port} failed: {exc}")
                continue

            print(f"[obd] adapter found on {port}!")
            break
        else:
            print("[obd] no adapter found")

    @property
    def alternator_current(self) -> float:
        resp = self._split_hex(self.execute("220551"))

        if len(resp) >= 5 and resp[0] == "62" and resp[1] == "05" and resp[2] == "51":
            a = int(resp[3], 16)
            b = int(resp[4], 16)
            return (a * 256 + b) / 100.0

        return 0.0

    @property
    def air_conditioner_on(self) -> int:
        resp = self._split_hex(self.execute("22099B"))

        if len(resp) == 5 and resp[0] == "62" and resp[1] == "09" and resp[2] == "9B":
            return int(resp[3], 16)

        return 0

    @property
    def fuel_tank_level(self) -> Optional[int]:
        resp = self._split_hex(self.execute("012F"))

        if len(resp) == 3 and resp[0] == "41" and resp[1] == "2F":
            a = int(resp[2], 16)
            return int(a * 100 / 255)

        return None

    @property
    def rpm(self) -> int:
        resp = self._split_hex(self.execute("010C"))

        if len(resp) == 4 and resp[0] == "41" and resp[1] == "0C":
            a = int(resp[2], 16)
            b = int(resp[3], 16)
            return int(((a * 256) + b) / 4)

        return 0


class VanOBDDriver:
    _dbus_service: Optional[VeDbusService] = None
    _dbus_tank_service: Optional[VeDbusService] = None
    _obd_conn: Optional[VanOBDConnection] = None

    def start_obd(self):
        self._obd_conn = VanOBDConnection()
        self._obd_conn.detect_adapter()

    def register_dbus(self):
        DBusGMainLoop(set_as_default=True)

        self._dbus_service = VeDbusService(
            "com.victronenergy.obd", dbus.SystemBus(private=True), register=False
        )
        self._dbus_service.add_mandatory_paths(
            processname="odb_dbus",
            processversion="1.0",
            connection="USB",
            deviceinstance=420,
            productid=42069,
            productname="vLinker FS USB",
            firmwareversion="1.0",
            hardwareversion="1.0",
            connected="1",
        )
        self._dbus_service.register()
        self._dbus_service.add_path("/Van0/RPM", 0, gettextcallback=lambda p, v: f"{int(v)} rpm")
        self._dbus_service.add_path(
            "/Van0/AirConditionerOn", 0, gettextcallback=lambda p, v: "On" if v == 1.0 else "Off"
        )
        self._dbus_service.add_path(
            "/Van0/AlternatorCurrent", 0.0, gettextcallback=lambda p, v: f"{float(v):.1f} A"
        )

        self._dbus_tank_service = VeDbusService(
            "com.victronenergy.tank.van", dbus.SystemBus(private=True), register=False
        )
        self._dbus_tank_service.add_mandatory_paths(
            processname="odb_dbus_tank",
            processversion="1.0",
            connection="USB",
            deviceinstance=420,
            productid=42069,
            productname="Van Fuel Tank",
            firmwareversion="1.0",
            hardwareversion="1.0",
            connected=1,
        )
        self._dbus_tank_service.register()
        self._dbus_tank_service.add_path(
            "/Level", 0.0, gettextcallback=lambda p, v: f"{round(v, 2)}%"
        )
        self._dbus_tank_service.add_path("/FluidType", 6, gettextcallback=lambda p, v: "Gasoline")
        self._dbus_tank_service.add_path(
            "/Capacity", 0.0946353, gettextcallback=lambda p, v: f"{round(v, 2)}"
        )
        self._dbus_tank_service.add_path(
            "/CustomName", "Van Fuel Tank", writeable=True, gettextcallback=lambda p, v: v
        )
        self._dbus_tank_service.add_path(
            "/Remaining", 0.0, gettextcallback=lambda p, v: f"{round(v, 2)}"
        )
        self._dbus_tank_service.add_path("/Status", 0, gettextcallback=lambda p, v: f"{v}")

        print(f"[obd] dbus services registered")

    def tick(self) -> bool:
        try:
            if self._obd_conn.port is None:
                self._obd_conn.detect_adapter()
                return True

            self._dbus_service["/Van0/RPM"] = self._obd_conn.rpm
            self._dbus_service["/Van0/AirConditionerOn"] = self._obd_conn.air_conditioner_on
            self._dbus_service["/Van0/AlternatorCurrent"] = self._obd_conn.alternator_current

            fuel_tank_level = self._obd_conn.fuel_tank_level
            if fuel_tank_level is None:
                self._dbus_tank_service["/Status"] = 1
            else:
                self._dbus_tank_service["/Status"] = 0
                self._dbus_tank_service["/Level"] = fuel_tank_level
                self._dbus_tank_service["/Remaining"] = (fuel_tank_level / 100.0) * 0.0946353
        except Exception as exc:
            print(f"[obd] polling error: {exc}")

            self._obd_conn.disconnect()

        return True


def main():
    print("[obd] starting service ...")

    driver = VanOBDDriver()
    driver.start_obd()
    driver.register_dbus()

    GLib.timeout_add(2000, driver.tick)
    GLib.MainLoop().run()


if __name__ == "__main__":
    main()
