"""Typed result models returned by the public device interface."""

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class DeviceStatus:
    """Current setpoints, reported limits, and output state.

    Attributes:
        set_voltage: Device-reported voltage setpoint in volts.
        set_current: Device-reported current setpoint in amperes.
        output_enabled: Whether the device reports its output as enabled.
        voltage_limit: Device-reported upper voltage limit in volts.
        current_limit: Device-reported upper current limit in amperes.
    """

    set_voltage: float
    set_current: float
    output_enabled: bool
    voltage_limit: float
    current_limit: float


@dataclass(frozen=True, slots=True)
class Measurements:
    """Output measurements returned by an explicit synchronous read.

    Attributes:
        output_voltage: Measured output voltage in volts.
        output_current: Measured output current in amperes.
        output_power: Measured output power in watts.
    """

    output_voltage: float
    output_current: float
    output_power: float


@dataclass(frozen=True, slots=True)
class DeviceInfo:
    """Device identity and version strings.

    Attributes:
        model: Device model identifier.
        hardware_version: Device hardware revision.
        firmware_version: Device firmware revision.
    """

    model: str
    hardware_version: str
    firmware_version: str


@dataclass(frozen=True, slots=True)
class ProtectionSettings:
    """Verified OPP, OTP, and LVP thresholds; OVP/OCP are not included.

    Attributes:
        over_power_w: Over-power threshold in watts.
        over_temperature_c: Over-temperature threshold in degrees Celsius.
        low_voltage_v: Low-voltage threshold in volts.
    """

    over_power_w: float
    over_temperature_c: float
    low_voltage_v: float


@dataclass(frozen=True, slots=True)
class Preset:
    """Voltage and current values stored in one device preset slot.

    Attributes:
        voltage: Preset voltage in volts.
        current: Preset current limit in amperes.
    """

    voltage: float
    current: float


@dataclass(frozen=True, slots=True)
class SystemSettings:
    """Verified non-buzzer system settings read from the target device.

    Attributes:
        brightness: Display brightness level from 0 through 10.
        metering_enabled: Whether metering is enabled.
    """

    brightness: int
    metering_enabled: bool
