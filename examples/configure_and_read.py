"""Output-OFF configuration round-trip example for the FNIRSI DPS150.

Defaults to a dry-run read of current settings. Pass ``--apply`` alongside one
or more configuration flags while output is OFF to write and read back settings;
by default original values are restored before closing unless ``--keep`` is set.
"""

from __future__ import annotations

import argparse
import sys

from fnirsi_dps150 import (
    DPS150,
    DeviceSnapshot,
    DPS150Error,
    Preset,
    find_ports,
)


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


def _validate_args(args: argparse.Namespace) -> None:
    """Validate CLI flag combinations before opening any serial port."""
    preset_flags = (args.preset_slot, args.preset_voltage, args.preset_current)
    provided_preset_flags = sum(value is not None for value in preset_flags)
    if 0 < provided_preset_flags < len(preset_flags):
        raise ValueError(
            "--preset-slot, --preset-voltage, and --preset-current must all be provided together."
        )
    has_updates = any(
        value is not None
        for value in (
            args.voltage,
            args.current,
            args.brightness,
            args.volume,
            args.preset_slot,
        )
    )
    if args.apply and not has_updates:
        raise ValueError(
            "--apply requires at least one setting option "
            "(--voltage, --current, --brightness, --volume, or --preset-slot)."
        )


def _print_settings_summary(label: str, snapshot: DeviceSnapshot, slot: int | None) -> None:
    """Print key output-OFF configuration values from one snapshot."""
    print(
        f"{label}: "
        f"set=({snapshot.set_voltage:.4f} V, {snapshot.set_current:.4f} A), "
        f"brightness={snapshot.system_settings.brightness}, "
        f"volume={snapshot.system_settings.volume}, "
        f"output={'ON' if snapshot.output_enabled else 'OFF'}"
    )
    if slot is not None:
        preset = snapshot.presets[slot - 1]
        print(f"  M{slot}: ({preset.voltage:.4f} V, {preset.current:.4f} A)")


def _apply_updates(
    device: DPS150,
    args: argparse.Namespace,
) -> tuple[bool, bool, bool, bool, bool]:
    """Write requested configuration updates without altering output state."""
    changed_voltage = False
    changed_current = False
    changed_brightness = False
    changed_volume = False
    changed_preset = False

    if args.voltage is not None and args.current is not None:
        changed_voltage = True
        changed_current = True
        device.set_setpoints(args.voltage, args.current)
    elif args.voltage is not None:
        changed_voltage = True
        device.set_voltage(args.voltage)
    elif args.current is not None:
        changed_current = True
        device.set_current(args.current)

    if args.brightness is not None:
        changed_brightness = True
        device.set_brightness(args.brightness)

    if args.volume is not None:
        changed_volume = True
        device.set_volume(args.volume)

    if args.preset_slot is not None:
        changed_preset = True
        device.set_preset(
            args.preset_slot,
            Preset(voltage=args.preset_voltage, current=args.preset_current),
        )

    return (
        changed_voltage,
        changed_current,
        changed_brightness,
        changed_volume,
        changed_preset,
    )


def _restore_initial_state(
    device: DPS150,
    initial: DeviceSnapshot,
    args: argparse.Namespace,
    changed: tuple[bool, bool, bool, bool, bool],
) -> None:
    """Restore original setpoints, brightness, volume, and preset while OFF."""
    (
        changed_voltage,
        changed_current,
        changed_brightness,
        changed_volume,
        changed_preset,
    ) = changed
    if not any(changed):
        return

    status = device.get_status()
    if status.output_enabled:
        raise RuntimeError(
            "Output became enabled; refusing to restore settings automatically."
        )

    if changed_voltage and changed_current:
        device.set_setpoints(initial.set_voltage, initial.set_current)
    elif changed_voltage:
        device.set_voltage(initial.set_voltage)
    elif changed_current:
        device.set_current(initial.set_current)

    if changed_brightness:
        device.set_brightness(initial.system_settings.brightness)
    if changed_volume:
        device.set_volume(initial.system_settings.volume)
    if changed_preset and args.preset_slot is not None:
        device.set_preset(args.preset_slot, initial.presets[args.preset_slot - 1])

    restored = device.get_snapshot()
    _print_settings_summary("Restored", restored, args.preset_slot)


def _build_parser() -> argparse.ArgumentParser:
    """Build the command-line parser for output-OFF configuration."""
    parser = argparse.ArgumentParser(
        description=(
            "Inspect DPS150 settings (default dry-run) or apply output-OFF "
            "updates with readback confirmation."
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
        default=1.0,
        help="Serial I/O timeout in seconds (default: 1.0).",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Actually write the requested settings while output is OFF.",
    )
    parser.add_argument(
        "--keep",
        action="store_true",
        help="Keep applied changes instead of restoring original settings before exit.",
    )
    parser.add_argument("--voltage", type=float, help="Target voltage setpoint (V).")
    parser.add_argument("--current", type=float, help="Target current limit (A).")
    parser.add_argument("--brightness", type=int, help="Target brightness (0..14).")
    parser.add_argument("--volume", type=int, help="Target buzzer volume (0..10).")
    parser.add_argument("--preset-slot", type=int, help="Target preset slot (1..6).")
    parser.add_argument("--preset-voltage", type=float, help="Preset voltage (V).")
    parser.add_argument("--preset-current", type=float, help="Preset current (A).")
    return parser


def main(argv: list[str] | None = None) -> int:
    """Run the output-OFF configuration inspection/round-trip example.

    Args:
        argv: Optional command-line argument list.

    Returns:
        Exit code (``0`` on success, ``1`` on validation or device error).
    """
    args = _build_parser().parse_args(argv)
    try:
        _validate_args(args)
        with _create_device(args.port, args.serial_number, args.timeout) as device:
            initial = device.get_snapshot()
            _print_settings_summary("Initial", initial, args.preset_slot)
            if not args.apply:
                print("Dry-run only (pass --apply with output OFF to write changes).")
                return 0
            if initial.output_enabled:
                raise RuntimeError(
                    "Device output is currently ON; refusing to run configuration example."
                )

            changed = (False, False, False, False, False)
            try:
                changed = _apply_updates(device, args)
                updated = device.get_snapshot()
                _print_settings_summary("Applied", updated, args.preset_slot)
            finally:
                if not args.keep and any(changed):
                    try:
                        _restore_initial_state(device, initial, args, changed)
                    except (DPS150Error, RuntimeError, ValueError) as restore_error:
                        print(
                            f"Warning: failed to restore initial settings: {restore_error}",
                            file=sys.stderr,
                        )
                        raise
    except (DPS150Error, RuntimeError, ValueError) as error:
        print(f"Error: {error}", file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
