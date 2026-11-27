"""Explicit opt-in controlled output-ON and metering example for FNIRSI DPS150.

This script does NOT open the serial port or enable output unless the caller
passes ``--confirm-load`` along with explicit ``--voltage`` and ``--current``
targets within conservative low-power ceilings (``<= 10.0 V`` and
``<= 0.10 A``). Output shutdown is verified before restoring initial setpoints.
"""

from __future__ import annotations

import argparse
import math
import struct
import sys
import time
from typing import Final

from fnirsi_dps150 import (
    DPS150,
    DeviceSnapshot,
    DPS150Error,
    MeteringReadings,
    find_ports,
)

_MAX_SAFE_VOLTAGE: Final[float] = 10.0
_MAX_SAFE_CURRENT: Final[float] = 0.10
_PAUSE_SETTLE_SECONDS: Final[float] = 0.25


def _resolve_port(requested_port: str | None) -> str:
    """Resolve the target serial port explicitly or via USB VID/PID lookup."""
    if requested_port is not None:
        return requested_port
    discovered = find_ports()
    if not discovered:
        raise RuntimeError(
            "No FNIRSI DPS150 serial port found (VID=0x2E3C, PID=0x5740). "
            "Pass --port explicitly."
        )
    return discovered[0]


def _create_device(
    port: str | None,
    serial_number: str | None,
    timeout: float,
) -> DPS150:
    """Create a :class:`DPS150` instance by port or USB VCP serial number."""
    if serial_number is not None:
        return DPS150(serial_number=serial_number, timeout=timeout)
    return DPS150(port=_resolve_port(port), timeout=timeout)


def _float32_value(value: float) -> float:
    """Return the exact IEEE-754 float32 representation sent on the wire."""
    return float(struct.unpack("<f", struct.pack("<f", value))[0])


def _validate_parameters(args: argparse.Namespace) -> tuple[float, float]:
    """Validate CLI inputs and low-power safety caps before opening hardware."""
    if not math.isfinite(args.duration) or args.duration <= 0:
        raise ValueError("--duration must be a finite positive number of seconds.")
    if not math.isfinite(args.interval) or args.interval <= 0:
        raise ValueError("--interval must be a finite positive number of seconds.")
    if args.voltage is None or args.current is None:
        raise ValueError("--voltage and --current are required with --confirm-load.")
    if not math.isfinite(args.voltage) or args.voltage < 0:
        raise ValueError("--voltage must be a finite non-negative number.")
    if not math.isfinite(args.current) or args.current < 0:
        raise ValueError("--current must be a finite non-negative number.")
    if args.voltage > _MAX_SAFE_VOLTAGE:
        raise ValueError(
            f"--voltage {args.voltage} V exceeds example safety cap of {_MAX_SAFE_VOLTAGE} V."
        )
    if args.current > _MAX_SAFE_CURRENT:
        raise ValueError(
            f"--current {args.current} A exceeds example safety cap of {_MAX_SAFE_CURRENT} A."
        )
    return _float32_value(args.voltage), _float32_value(args.current)


def _sample_window(device: DPS150, duration: float, interval: float) -> None:
    """Poll output telemetry and metering counters across the enabled window."""
    deadline = time.monotonic() + duration
    sample_index = 0
    while True:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            break
        time.sleep(min(interval, remaining))
        sample_index += 1
        measurements = device.get_measurements()
        mode = device.get_regulation_mode()
        protection_code = device.get_protection_status_code()
        protection_status = device.get_protection_status()
        metering = device.get_metering()
        protection_label = (
            protection_status.name
            if protection_status is not None
            else f"CODE_{protection_code}"
        )
        print(
            f"  sample {sample_index}: "
            f"{measurements.output_voltage:.4f} V, "
            f"{measurements.output_current:.4f} A, "
            f"{measurements.output_power:.4f} W, "
            f"mode={mode.name}, "
            f"prot={protection_label}, "
            f"metering=({metering.capacity_ah:.6f} Ah, {metering.energy_wh:.6f} Wh)",
            flush=True,
        )


def _cleanup_device(
    device: DPS150,
    initial: DeviceSnapshot | None,
    setpoints_changed: bool,
    metering_changed: bool,
    output_may_be_on: bool,
) -> None:
    """Ensure output is confirmed OFF before resetting metering or restoring state."""
    if initial is None:
        return

    status = device.get_status()
    if output_may_be_on or status.output_enabled:
        device.set_output(False)
        status = device.get_status()
        if status.output_enabled:
            raise RuntimeError(
                "Device still reports output enabled after shutdown; switch OFF at panel."
            )

    if metering_changed:
        device.reset_metering()
        device.set_metering_enabled(initial.system_settings.metering_enabled)

    if setpoints_changed:
        device.set_setpoints(initial.set_voltage, initial.set_current)
        restored = device.get_status()
        if restored.output_enabled:
            raise RuntimeError(
                "Output became enabled while restoring original setpoints."
            )
        if (
            restored.set_voltage != initial.set_voltage
            or restored.set_current != initial.set_current
        ):
            raise RuntimeError("Original setpoints were not restored cleanly.")


def _build_parser() -> argparse.ArgumentParser:
    """Build the command-line parser for controlled output and metering."""
    parser = argparse.ArgumentParser(
        description=(
            "Controlled low-power DPS150 output and metering workflow. "
            "Requires --confirm-load before opening or enabling the device."
        ),
    )
    selector = parser.add_mutually_exclusive_group()
    selector.add_argument("--port", help="Serial port name. Auto-detected if omitted.")
    selector.add_argument(
        "--serial-number",
        help="USB VCP serial number matched across VID=0x2E3C.",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=2.0,
        help="Serial I/O timeout in seconds (default: 2.0).",
    )
    parser.add_argument(
        "--voltage",
        type=float,
        help=f"Target voltage in V (max {_MAX_SAFE_VOLTAGE} V).",
    )
    parser.add_argument(
        "--current",
        type=float,
        help=f"Target current limit in A (max {_MAX_SAFE_CURRENT} A).",
    )
    parser.add_argument(
        "--duration",
        type=float,
        default=5.0,
        help="Enabled sampling duration in seconds (default: 5.0).",
    )
    parser.add_argument(
        "--interval",
        type=float,
        default=1.0,
        help="Polling interval in seconds (default: 1.0).",
    )
    parser.add_argument(
        "--confirm-load",
        action="store_true",
        help="Required opt-in confirming an appropriate test load and operator presence.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    """Run the opt-in controlled output and metering example.

    Args:
        argv: Optional command-line argument list.

    Returns:
        Exit code (``0`` on success, ``1`` on failure).
    """
    args = _build_parser().parse_args(argv)
    if not args.confirm_load:
        print(
            "Output NOT enabled: pass --confirm-load with --voltage and --current "
            f"(caps: <= {_MAX_SAFE_VOLTAGE} V, <= {_MAX_SAFE_CURRENT} A) "
            "when an appropriate load is connected and attended."
        )
        return 0

    try:
        target_voltage, target_current = _validate_parameters(args)
        paused_readings: MeteringReadings | None = None
        initial: DeviceSnapshot | None = None
        setpoints_changed = False
        metering_changed = False
        output_may_be_on = False

        with _create_device(args.port, args.serial_number, args.timeout) as device:
            initial = device.get_snapshot()
            if initial.output_enabled:
                raise RuntimeError(
                    "Device output is already enabled; refusing to run example."
                )
            if target_voltage > initial.voltage_limit:
                raise ValueError(
                    f"Target voltage {target_voltage} V exceeds device limit "
                    f"{initial.voltage_limit} V."
                )
            if target_current > initial.current_limit:
                raise ValueError(
                    f"Target current {target_current} A exceeds device limit "
                    f"{initial.current_limit} A."
                )

            try:
                setpoints_changed = True
                device.set_setpoints(target_voltage, target_current)
                status = device.get_status()
                if status.output_enabled:
                    raise RuntimeError("Output became enabled while setting targets.")

                metering_changed = True
                device.set_metering_enabled(False)
                device.set_metering_enabled(True)

                output_may_be_on = True
                device.set_output(True)
                enabled_status = device.get_status()
                if not enabled_status.output_enabled:
                    raise RuntimeError("Device did not report output enabled.")

                print(
                    f"Output enabled on {device.port}: "
                    f"{enabled_status.set_voltage:.4f} V / "
                    f"{enabled_status.set_current:.4f} A"
                )
                _sample_window(device, args.duration, args.interval)

                device.set_metering_enabled(False)
                time.sleep(_PAUSE_SETTLE_SECONDS)
                paused_readings = device.get_metering()

                device.set_output(False)
                output_may_be_on = False
                stopped_status = device.get_status()
                if stopped_status.output_enabled:
                    raise RuntimeError("Device still reports output enabled after disable.")
            finally:
                try:
                    _cleanup_device(
                        device=device,
                        initial=initial,
                        setpoints_changed=setpoints_changed,
                        metering_changed=metering_changed,
                        output_may_be_on=output_may_be_on,
                    )
                except (DPS150Error, RuntimeError, ValueError) as cleanup_error:
                    print(
                        f"Warning: cleanup failed: {cleanup_error}",
                        file=sys.stderr,
                    )
                    raise
    except (DPS150Error, RuntimeError, ValueError) as error:
        print(f"Error: {error}", file=sys.stderr)
        return 1

    print(f"Completed safely; paused metering before reset: {paused_readings}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
