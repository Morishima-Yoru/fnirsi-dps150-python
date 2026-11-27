"""Typed result models returned by the public device interface."""

from dataclasses import dataclass

from .definitions.namespace import ProtectionStatus, RegulationMode


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
    """Verified OPP, OTP, and LVP thresholds used by read/write settings methods.

    Each threshold also has an individual scalar getter and setter; OVP and
    OCP thresholds are exposed through separate scalar methods.

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
    """Verified system settings read from the target device.

    Attributes:
        brightness: Display brightness level from 0 through 14.
        metering_enabled: Whether metering is enabled.
        volume: Buzzer volume level from 0 through 10 (0 is muted).
    """

    brightness: int
    metering_enabled: bool
    volume: int = 0


@dataclass(frozen=True, slots=True)
class MeteringReadings:
    """Accumulated output capacity and energy readings.

    Attributes:
        capacity_ah: Device-reported accumulated capacity in ampere-hours.
        energy_wh: Device-reported accumulated energy in watt-hours.
    """

    capacity_ah: float
    energy_wh: float


@dataclass(frozen=True, slots=True)
class ProtectionLimits:
    """Device-reported upper ceilings for configurable protection thresholds.

    Attributes:
        over_voltage_v: Maximum configurable OVP threshold in volts.
        over_current_a: Maximum configurable OCP threshold in amperes.
        over_power_w: Maximum configurable OPP threshold in watts.
        over_temperature_c: Maximum configurable OTP threshold in degrees Celsius.
        low_voltage_v: Maximum configurable LVP threshold in volts.
    """

    over_voltage_v: float
    over_current_a: float
    over_power_w: float
    over_temperature_c: float
    low_voltage_v: float


@dataclass(frozen=True, slots=True)
class DeviceSnapshot:
    """Typed full-state snapshot returned by ``GET 0xFF``.

    Attributes:
        input_voltage: Measured input voltage in volts.
        set_voltage: Device-reported voltage setpoint in volts.
        set_current: Device-reported current setpoint in amperes.
        measurements: Measured output voltage, current, and power.
        temperature: Reported device temperature in degrees Celsius.
        presets: Six stored preset slots (M1 through M6).
        over_voltage_threshold: Configured OVP threshold in volts.
        over_current_threshold: Configured OCP threshold in amperes.
        protection_settings: Configured OPP, OTP, and LVP thresholds.
        system_settings: Verified display brightness, buzzer volume, and metering enable state.
        metering: Accumulated output capacity and energy
            (:class:`MeteringReadings`).
        output_enabled: Whether the device reports its output as enabled.
        protection_code: Raw protection status byte.
        protection_status: Mapped :class:`ProtectionStatus` if known, else ``None``.
        regulation_mode: Reported :class:`RegulationMode`.
        voltage_limit: Device-reported upper voltage limit in volts.
        current_limit: Device-reported upper current limit in amperes.
        protection_limits: Device-reported protection threshold ceilings if
            present in the snapshot, otherwise ``None``.
    """

    input_voltage: float
    set_voltage: float
    set_current: float
    measurements: Measurements
    temperature: float
    presets: tuple[Preset, ...]
    over_voltage_threshold: float
    over_current_threshold: float
    protection_settings: ProtectionSettings
    system_settings: SystemSettings
    metering: MeteringReadings
    output_enabled: bool
    protection_code: int
    protection_status: ProtectionStatus | None
    regulation_mode: RegulationMode
    voltage_limit: float
    current_limit: float
    protection_limits: ProtectionLimits | None
