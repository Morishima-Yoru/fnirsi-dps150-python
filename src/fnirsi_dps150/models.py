"""Typed result models returned by the public device interface."""

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class DeviceStatus:
    """Minimal status snapshot available before core controls are added.

    Attributes:
        output_enabled: Whether the device reports its output as enabled.
    """

    output_enabled: bool
