import dbus
from enum import Enum


class PhoenixState(Enum):
    OFF = 0
    LOW_POWER = 1
    FAULT = 2
    INVERTING = 9


class PhoenixInverter:
    VEDIRECT_ON_CMD = "800020002"
    VEDIRECT_OFF_CMD = "800020004"
    DBUS_OBJ_TYPE = "com.victronenergy.BusItem"
    DBUS_SERVICE_PREFIX = "com.victronenergy.inverter."
    DBUS_PATH_AC_CURR = "/Ac/Out/L1/I"
    DBUS_PATH_DC_VOLT = "/Dc/0/Voltage"
    DBUS_PATH_STATE = "/State"

    def __init__(self, tty):
        self._bus = dbus.SystemBus()
        self._tty = tty.removeprefix("/dev/")
        self._ac_curr_iface = self._get_iface(self.DBUS_PATH_AC_CURR)
        self._dc_volt_iface = self._get_iface(self.DBUS_PATH_DC_VOLT)
        self._state_iface = self._get_iface(self.DBUS_PATH_STATE)

    def _get_iface(self, path):
        obj = self._bus.get_object(f"{self.DBUS_SERVICE_PREFIX}{self._tty}", path)
        return dbus.Interface(obj, self.DBUS_OBJ_TYPE)

    @staticmethod
    def _checksum(cmd):
        total = int(cmd[0])

        for i in range(1, len(cmd), 2):
            total += int(cmd[i : i + 2], 16)

        return f"{(85 - total) & 0xFF:02X}"

    def _send_cmd(self, cmd):
        with open(f"/dev/{self._tty}", "wt") as fp:
            fp.write(f":{cmd}{self._checksum(cmd)}\n")

    @property
    def ac_current(self):
        return round(self._ac_curr_iface.GetValue(), 2)

    @property
    def dc_voltage(self):
        return round(self._dc_volt_iface.GetValue(), 2)

    @property
    def state(self):
        return PhoenixState(self._state_iface.GetValue())

    def on(self):
        print(f"[phoenix] turning on")
        self._send_cmd("800020002")

    def off(self):
        print(f"[phoenix] turning off")
        self._send_cmd("800020004")
