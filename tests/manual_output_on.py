"""Separately invoked, manually gated output-enable hardware check."""

import math
import os

from fnirsi_dps150 import DPS150, DeviceStatus

_OPT_IN_VARIABLE = "DPS150_ALLOW_OUTPUT_ON_TEST"
_NO_LOAD_CONFIRMATION = "NO LOAD CONNECTED"


def _read_ceiling(name: str) -> float:
    try:
        ceiling = float(input(f"Maximum allowed output {name}: "))
    except ValueError as error:
        raise ValueError(f"The {name} ceiling must be a finite positive number.") from error
    if not math.isfinite(ceiling) or ceiling <= 0:
        raise ValueError(f"The {name} ceiling must be a finite positive number.")
    return ceiling


def _confirm_test() -> tuple[float, float]:
    if os.environ.get(_OPT_IN_VARIABLE) != "1":
        raise SystemExit(f"Set {_OPT_IN_VARIABLE}=1 to opt in to this hardware test.")
    if input(f"Confirm no load by typing '{_NO_LOAD_CONFIRMATION}': ") != _NO_LOAD_CONFIRMATION:
        raise SystemExit("No-load confirmation did not match; output remains untouched.")
    return _read_ceiling("voltage (V)"), _read_ceiling("current (A)")


def _validate_ceilings(
    status: DeviceStatus,
    voltage_ceiling: float,
    current_ceiling: float,
) -> None:
    if status.set_voltage > voltage_ceiling:
        raise RuntimeError("The current voltage setpoint exceeds the supplied ceiling.")
    if status.set_current > current_ceiling:
        raise RuntimeError("The current limit exceeds the supplied ceiling.")


def main() -> None:
    """Run one explicitly gated output-enable hardware check."""
    voltage_ceiling, current_ceiling = _confirm_test()
    device = DPS150(port=os.environ.get("DPS150_PORT", "COM64"), timeout=2.0)
    device.open()
    try:
        initial_status = device.get_status()
        if initial_status.output_enabled:
            raise RuntimeError("Output was already enabled; refusing to run the test.")
        _validate_ceilings(initial_status, voltage_ceiling, current_ceiling)

        device.set_output(True)
        enabled_status = device.get_status()
        if not enabled_status.output_enabled:
            raise RuntimeError("The device did not report output enabled after the command.")
        _validate_ceilings(enabled_status, voltage_ceiling, current_ceiling)
    finally:
        try:
            device.set_output(False)
            if device.get_status().output_enabled:
                raise RuntimeError("The device still reports output enabled after shutdown.")
        finally:
            device.close()


if __name__ == "__main__":
    main()
