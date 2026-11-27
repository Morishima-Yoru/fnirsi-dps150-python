"""Read-only snapshot inspection example for the FNIRSI DPS150.

Discovers or opens a DPS150 serial port, reads device identity and the full
status snapshot once, and closes cleanly without modifying any settings or
output state.
"""

from __future__ import annotations

import argparse
import sys

from fnirsi_dps150 import (
    DPS150,
    DeviceInfo,
    DeviceSnapshot,
    DPS150Error,
    find_ports,
)


def _resolve_port(requested_port: str | None) -> str:
    """Resolve the target serial port explicitly or via USB VID/PID lookup.

    Args:
        requested_port: Explicit serial port name if provided by the user.

    Returns:
        Selected serial port name.

    Raises:
        RuntimeError: If no port was provided and auto-discovery found none.
    """
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


def _format_snapshot(
    port: str,
    info: DeviceInfo,
    snapshot: DeviceSnapshot,
    serial_number: str | None = None,
) -> str:
    """Format device identity and snapshot fields into human-readable lines.

    Args:
        port: Serial port used for the read.
        info: Device model and firmware/hardware version strings.
        snapshot: Full device state snapshot.

    Returns:
        Formatted multi-line summary string.
    """
    output_state = "ON" if snapshot.output_enabled else "OFF"
    metering_state = "enabled" if snapshot.system_settings.metering_enabled else "paused"
    protection_name = (
        snapshot.protection_status.name
        if snapshot.protection_status is not None
        else "UNKNOWN"
    )
    lines = [
        f"Port:        {port}",
        *(
            [f"Serial:      {serial_number}"]
            if serial_number is not None
            else []
        ),
        f"Device:      {info.model} (HW {info.hardware_version}, FW {info.firmware_version})",
        f"Output:      {output_state} ({snapshot.regulation_mode.name})",
        f"Input:       {snapshot.input_voltage:.3f} V",
        f"Temperature: {snapshot.temperature:.2f} C",
        (
            f"Setpoints:   {snapshot.set_voltage:.4f} V / {snapshot.set_current:.4f} A "
            f"(limits: {snapshot.voltage_limit:.4f} V / {snapshot.current_limit:.4f} A)"
        ),
        (
            f"Measured:    {snapshot.measurements.output_voltage:.4f} V, "
            f"{snapshot.measurements.output_current:.4f} A, "
            f"{snapshot.measurements.output_power:.4f} W"
        ),
        (
            f"Metering:    {metering_state} "
            f"({snapshot.metering.capacity_ah:.6f} Ah, "
            f"{snapshot.metering.energy_wh:.6f} Wh)"
        ),
        (
            f"System:      brightness={snapshot.system_settings.brightness}/14, "
            f"volume={snapshot.system_settings.volume}/10"
        ),
        f"Protection:  {protection_name} (raw code {snapshot.protection_code})",
        (
            f"Thresholds:  OVP={snapshot.over_voltage_threshold:.3f} V, "
            f"OCP={snapshot.over_current_threshold:.3f} A, "
            f"OPP={snapshot.protection_settings.over_power_w:.3f} W, "
            f"OTP={snapshot.protection_settings.over_temperature_c:.2f} C, "
            f"LVP={snapshot.protection_settings.low_voltage_v:.3f} V"
        ),
    ]
    if snapshot.protection_limits is not None:
        limits = snapshot.protection_limits
        lines.append(
            f"Ceilings:    OVP={limits.over_voltage_v:.3f} V, "
            f"OCP={limits.over_current_a:.3f} A, "
            f"OPP={limits.over_power_w:.3f} W, "
            f"OTP={limits.over_temperature_c:.2f} C, "
            f"LVP={limits.low_voltage_v:.3f} V"
        )
    lines.append("Presets:")
    for slot, preset in enumerate(snapshot.presets, start=1):
        lines.append(f"  M{slot}: {preset.voltage:.4f} V / {preset.current:.4f} A")
    return "\n".join(lines)


def _build_parser() -> argparse.ArgumentParser:
    """Build the command-line parser for read-only inspection."""
    parser = argparse.ArgumentParser(
        description="Read and print a synchronous DPS150 device snapshot.",
    )
    selector = parser.add_mutually_exclusive_group()
    selector.add_argument(
        "--port",
        help="Serial port name (for example COM64 or /dev/ttyACM0). Auto-detected if omitted.",
    )
    selector.add_argument(
        "--serial-number",
        help="USB VCP serial number (for example 10F5D04E4486) matched across VID=0x2E3C.",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=1.0,
        help="Serial I/O timeout in seconds (default: 1.0).",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    """Run the read-only snapshot inspection example.

    Args:
        argv: Optional command-line argument list.

    Returns:
        Exit code (``0`` on success, ``1`` on failure).
    """
    args = _build_parser().parse_args(argv)
    try:
        device = _create_device(args.port, args.serial_number, args.timeout)
        with device:
            info = device.get_device_info()
            snapshot = device.get_snapshot()
    except (DPS150Error, RuntimeError, ValueError) as error:
        print(f"Error: {error}", file=sys.stderr)
        return 1

    print(
        _format_snapshot(
            device.port,
            info,
            snapshot,
            serial_number=device.serial_number,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
