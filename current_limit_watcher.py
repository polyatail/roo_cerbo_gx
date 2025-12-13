#!/usr/bin/env python3
from devices.multiplus import MultiPlusInverter, MultiPlusACType
from devices.phoenix import PhoenixInverter, PhoenixState
from devices.system import VeSystem
from devices.van import VanOBD
import time

# TTYs for various devices
MULTIPLUS_TTY = "/dev/ttyS4"
PHOENIX_TTY = "/dev/ttyS5"
VAN_TTY = "/dev/ttyUSB0"

# Thresholds and limits
V_TURN_ON = 14.2
V_TURN_OFF = 13.6
CURR_LIMIT_LOW = 7.8
CURR_LIMIT_HIGH = 13.0
POLL_INTERVAL_SEC = 1


def main():
    multiplus = MultiPlusInverter(MULTIPLUS_TTY)
    phoenix = PhoenixInverter(PHOENIX_TTY)
    van = VanOBD(VAN_TTY)
    ve_system = VeSystem()

    print("[watcher] started; monitoring system...")

    while True:
        phoenix.read_telemetry_frame()

        print(
            f"[ac: {van.air_conditioner_on} rpm: {van.rpm}] "
            + f"[state: {phoenix.state.name} curr: {phoenix.ac_current} volt: {phoenix.dc_voltage}] "
            + f"[limit: {multiplus.ac1_current_limit} type: {multiplus.ac1_type.name}] "
            + f"[soc: {ve_system.dc_soc}]"
        )

        if (van.rpm > 0 and not van.air_conditioner_on) or ve_system.dc_soc < 5:
            if phoenix.ac_current > 0:
                if multiplus.ac1_current_limit > CURR_LIMIT_LOW:
                    multiplus.ac1_current_limit = CURR_LIMIT_LOW

                if multiplus.ac1_type != MultiPlusACType.GENERATOR:
                    multiplus.ac1_type = MultiPlusACType.GENERATOR
            else:
                if multiplus.ac1_current_limit == CURR_LIMIT_LOW:
                    multiplus.ac1_current_limit = CURR_LIMIT_HIGH

                if multiplus.ac1_type != MultiPlusACType.SHORE:
                    multiplus.ac1_type = MultiPlusACType.SHORE

            if phoenix.state != PhoenixState.INVERTING:
                phoenix.on()
        else:
            if phoenix.state == PhoenixState.INVERTING:
                phoenix.off()

                if multiplus.ac1_current_limit == CURR_LIMIT_LOW:
                    multiplus.ac1_current_limit = CURR_LIMIT_HIGH

                multiplus.ac1_type = MultiPlusACType.SHORE

        time.sleep(POLL_INTERVAL_SEC)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("[watcher] stopped by user")
