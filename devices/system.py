import dbus


class VeSystem:
    DBUS_OBJ_TYPE = "com.victronenergy.BusItem"
    DBUS_SERVICE = "com.victronenergy.system"
    DBUS_PATH_DC_SOC = "/Dc/Battery/Soc"

    def __init__(self):
        self._bus = dbus.SystemBus()
        self._dc_soc_iface = self._get_iface(self.DBUS_PATH_DC_SOC)

    def _get_iface(self, path):
        obj = self._bus.get_object(self.DBUS_SERVICE, path)
        return dbus.Interface(obj, self.DBUS_OBJ_TYPE)

    @property
    def dc_soc(self):
        return round(self._dc_soc_iface.GetValue(), 2)
