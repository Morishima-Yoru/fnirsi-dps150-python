"""Separately invoked, manually gated output-enable hardware check."""

import math
import os
import struct
from typing import Final

from fnirsi_dps150 import DPS150, DeviceStatus

_OPT_IN_VARIABLE: Final[str] = "DPS150_ALLOW_OUTPUT_ON_TEST"
_NO_LOAD_CONFIRMATION: Final[str] = "NO LOAD CONNECTED"


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


def _validate_device_limits(
    status: DeviceStatus,
    voltage_ceiling: float,
    current_ceiling: float,
) -> None:
    if voltage_ceiling > status.voltage_limit:
        raise RuntimeError("The voltage ceiling exceeds the device-reported limit.")
    if current_ceiling > status.current_limit:
        raise RuntimeError("The current ceiling exceeds the device-reported limit.")


def _float32_at_or_below(value: float) -> float:
    try:
        payload = struct.pack("<f", value)
    except (OverflowError, struct.error) as error:
        raise RuntimeError("The supplied ceiling is outside the float32 range.") from error
    encoded_value = struct.unpack("<f", payload)[0]
    if encoded_value > value:
        bits = struct.unpack("<I", payload)[0]
        payload = struct.pack("<I", bits - 1)
        encoded_value = struct.unpack("<f", payload)[0]
    return encoded_value


def main() -> None:
    """Run one explicitly gated output-enable hardware check."""
    voltage_ceiling, current_ceiling = _confirm_test()
    device = DPS150(port=os.environ.get("DPS150_PORT", "COM64"), timeout=2.0)
    device.open()
    initial_status: DeviceStatus | None = None
    setpoints_may_have_changed = False
    output_enable_attempted = False
    try:
        initial_status = device.get_status()
        if initial_status.output_enabled:
            raise RuntimeError("Output was already enabled; refusing to run the test.")
        _validate_device_limits(initial_status, voltage_ceiling, current_ceiling)
        test_voltage = _float32_at_or_below(voltage_ceiling)
        test_current = _float32_at_or_below(current_ceiling)

        setpoints_may_have_changed = True
        device.set_voltage(test_voltage)
        device.set_current(test_current)
        capped_status = device.get_status()
        if capped_status.output_enabled:
            raise RuntimeError("Output became enabled while capping setpoints.")
        _validate_ceilings(capped_status, voltage_ceiling, current_ceiling)

        output_enable_attempted = True
        device.set_output(True)
        enabled_status = device.get_status()
        if not enabled_status.output_enabled:
            raise RuntimeError("The device did not report output enabled after the command.")
        _validate_ceilings(enabled_status, voltage_ceiling, current_ceiling)
    finally:
        try:
            final_status: DeviceStatus | None = None
            if output_enable_attempted:
                device.set_output(False)
                final_status = device.get_status()
                if final_status.output_enabled:
                    raise RuntimeError(
                        "The device still reports output enabled after shutdown."
                    )
            elif setpoints_may_have_changed:
                final_status = device.get_status()
                if final_status.output_enabled:
                    device.set_output(False)
                    final_status = device.get_status()
                    if final_status.output_enabled:
                        raise RuntimeError(
                            "The device still reports output enabled after shutdown."
                        )

            if setpoints_may_have_changed and initial_status is not None:
                if final_status is None or final_status.output_enabled:
                    raise RuntimeError(
                        "Output is not confirmed OFF; refusing to restore setpoints."
                    )
                device.set_voltage(initial_status.set_voltage)
                device.set_current(initial_status.set_current)
                restored_status = device.get_status()
                if restored_status.output_enabled:
                    raise RuntimeError(
                        "Output became enabled while restoring the original setpoints."
                    )
                if (
                    restored_status.set_voltage != initial_status.set_voltage
                    or restored_status.set_current != initial_status.set_current
                ):
                    raise RuntimeError("The original setpoints were not restored.")
        finally:
            device.close()


if __name__ == "__main__":
    main()
