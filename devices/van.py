import dbus


class VanOBD:
    DBUS_OBJ_TYPE = "com.victronenergy.BusItem"
    DBUS_SERVICE_PREFIX = "com.victronenergy.obd."
    DBUS_PATH_AC_ON = "/Van0/AirConditionerOn"
    DBUS_PATH_ALT_CURR = "/Van0/AlternatorCurrent"
    DBUS_PATH_RPM = "/Van0/RPM"

    def __init__(self, tty):
        self._bus = dbus.SystemBus()
        self._tty = tty.removeprefix("/dev/")
        self._ac_on_iface = self._get_iface(self.DBUS_PATH_AC_ON)
        self._alt_curr_iface = self._get_iface(self.DBUS_PATH_ALT_CURR)
        self._rpm_iface = self._get_iface(self.DBUS_PATH_RPM)

    def _get_iface(self, path):
        # TODO(roo): Make this work with multiple different TTYs
        # obj = self._bus.get_object(f"{self.DBUS_SERVICE_PREFIX}{self._tty}", path)
        obj = self._bus.get_object(self.DBUS_SERVICE_PREFIX.removesuffix("."), path)
        return dbus.Interface(obj, self.DBUS_OBJ_TYPE)

    @property
    def air_conditioner_on(self):
        return bool(self._ac_on_iface.GetValue())

    @property
    def alternator_current(self):
        return round(self._alt_curr_iface.GetValue(), 2)

    @property
    def rpm(self):
        return round(self._rpm_iface.GetValue(), 2)
