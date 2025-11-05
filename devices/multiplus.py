import dbus
from enum import Enum


class MultiPlusState(Enum):
    OFF = 0
    LOW_POWER = 1
    FAULT = 2
    BULK = 3
    ABSORPTION = 4
    FLOAT = 5
    STORAGE = 6
    EQUALIZATION = 7
    PASSTHROUGH = 8
    INVERTING = 9
    POWER_ASSIST = 10
    POWER_SUPPLY = 11
    BULK_PROTECTION = 252


class MultiPlusACType(Enum):
    DISABLED = 0
    GRID = 1
    GENERATOR = 2
    SHORE = 3


class MultiPlusInverter:
    DBUS_OBJ_TYPE = "com.victronenergy.BusItem"
    DBUS_SERVICE_PREFIX = "com.victronenergy.vebus."
    DBUS_AC_CURR_LIMIT = "/Ac/In/1/CurrentLimit"
    DBUS_PATH_STATE = "/State"
    DBUS_PATH_AC1_TYPE = "/Settings/SystemSetup/AcInput1"

    def __init__(self, tty):
        self._bus = dbus.SystemBus()
        self._tty = tty.removeprefix("/dev/")
        self._ac_type_iface = self._get_iface(self.DBUS_PATH_AC1_TYPE)
        self._ac_curr_limit_iface = self._get_iface(self.DBUS_AC_CURR_LIMIT)
        self._state_iface = self._get_iface(self.DBUS_PATH_STATE)

    def _get_iface(self, path):
        obj = self._bus.get_object(f"{self.DBUS_SERVICE_PREFIX}{self._tty}", path)
        return dbus.Interface(obj, self.DBUS_OBJ_TYPE)

    @property
    def state(self) -> MultiPlusState:
        return MultiPlusState(round(self._state_iface.GetValue()))

    @property
    def ac1_type(self) -> MultiPlusACType:
        return MultiPlusACType(self._ac_type_iface.GetValue())

    @ac1_type.setter
    def ac1_type(self, value: MultiPlusACType):
        print(f"[multiplus] setting ac1 type to {value.name}")
        self._ac_type_iface.SetValue(value.value)

    @property
    def ac1_current_limit(self) -> float:
        return round(self._ac_curr_limit_iface.GetValue(), 2)

    @ac1_current_limit.setter
    def ac1_current_limit(self, value: float):
        print(f"[multiplus] setting current limit to {value}")
        self._ac_curr_limit_iface.SetValue(value)
