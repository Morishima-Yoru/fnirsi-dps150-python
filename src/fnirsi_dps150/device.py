"""Public synchronous device interface."""

from __future__ import annotations

import math
import struct
from types import TracebackType

from ._transport import _SerialTransport
from .definitions.exceptions import DPS150Error, DPS150ProtocolError
from .definitions.namespace import (
    _BRIGHTNESS_MAX,
    _BRIGHTNESS_MIN,
    _MEASUREMENTS_PAYLOAD_SIZE,
    _PRESET_SLOT_COUNT,
    _PRESET_SLOT_MIN,
    _STATUS_PAYLOAD_SIZE,
    _ProtocolCommand,
    _ProtocolType,
    _StatusOffset,
)
from .models import DeviceStatus, Measurements, Preset, SystemSettings


class DPS150:
    """Control one FNIRSI DPS150 over its USB virtual serial port.

    Construction stores connection settings only. It does not open the port or
    send a command to the device.
    """

    def __init__(self, port: str, timeout: float = 1.0) -> None:
        """Create a device handle without performing serial I/O.

        Args:
            port: Host serial port, such as ``COM3``.
            timeout: Finite positive timeout in seconds for serial I/O.

        Raises:
            ValueError: If the port or timeout is invalid.
        """
        if not isinstance(port, str) or not port.strip():
            raise ValueError("port must be a non-empty string.")
        if isinstance(timeout, bool) or not isinstance(timeout, (int, float)):
            raise ValueError("timeout must be a finite positive number.")
        try:
            timeout_seconds = float(timeout)
        except OverflowError as error:
            raise ValueError("timeout must be a finite positive number.") from error
        if not math.isfinite(timeout_seconds) or timeout_seconds <= 0:
            raise ValueError("timeout must be a finite positive number.")

        self._transport = _SerialTransport(port=port, timeout=timeout_seconds)

    def open(self) -> None:
        """Open the host port and send the session-connect handshake.

        No setpoint or output-control command is sent.

        Raises:
            :class:`~fnirsi_dps150.DPS150CommunicationError`: If opening or
                session setup fails.
        """
        if not self._transport.open():
            return
        try:
            self._transport.send(
                _ProtocolCommand.CONNECT,
                _ProtocolType.SESSION,
                b"\x01",
            )
        except DPS150Error:
            self._transport.close()
            raise

    def close(self) -> None:
        """Close the host serial port without sending a device command."""
        self._transport.close()

    def get_status(self) -> DeviceStatus:
        """Read setpoints, device-reported limits, and output state.

        Returns:
            A typed snapshot of the setpoints, reported limits, and output state.

        Raises:
            :class:`~fnirsi_dps150.DPS150ProtocolError`: If the response is
                malformed or incomplete.
            :class:`~fnirsi_dps150.DPS150ConnectionError`: If the device is not
                open.
            :class:`~fnirsi_dps150.DPS150CommunicationError`: If serial
                communication fails.
        """
        frame = self._transport.exchange(
            _ProtocolCommand.GET,
            _ProtocolType.STATUS,
            b"",
            expected_response=(_ProtocolCommand.GET, _ProtocolType.STATUS),
        )
        if len(frame.payload) < _STATUS_PAYLOAD_SIZE:
            raise DPS150ProtocolError("Status response is too short.")

        output_enabled = frame.payload[_StatusOffset.OUTPUT_ENABLED]
        if output_enabled not in (0, 1):
            raise DPS150ProtocolError("Status contains an invalid output state.")
        voltage_limit = _read_float32(
            frame.payload,
            _StatusOffset.VOLTAGE_LIMIT,
            "voltage limit",
        )
        current_limit = _read_float32(
            frame.payload,
            _StatusOffset.CURRENT_LIMIT,
            "current limit",
        )
        if voltage_limit < 0 or current_limit < 0:
            raise DPS150ProtocolError("Status contains a negative device limit.")
        return DeviceStatus(
            set_voltage=_read_float32(
                frame.payload,
                _StatusOffset.VOLTAGE_SETPOINT,
                "voltage setpoint",
            ),
            set_current=_read_float32(
                frame.payload,
                _StatusOffset.CURRENT_SETPOINT,
                "current setpoint",
            ),
            output_enabled=bool(output_enabled),
            voltage_limit=voltage_limit,
            current_limit=current_limit,
        )

    def get_measurements(self) -> Measurements:
        """Read output voltage, current, and power synchronously.

        Returns:
            A typed snapshot of the three output measurements.

        Raises:
            :class:`~fnirsi_dps150.DPS150ProtocolError`: If the response is
                malformed or contains non-finite values.
            :class:`~fnirsi_dps150.DPS150ConnectionError`: If the device is not
                open.
            :class:`~fnirsi_dps150.DPS150CommunicationError`: If serial
                communication fails.
        """
        frame = self._transport.exchange(
            _ProtocolCommand.GET,
            _ProtocolType.MEASUREMENTS,
            b"",
            expected_response=(
                _ProtocolCommand.GET,
                _ProtocolType.MEASUREMENTS,
            ),
        )
        if len(frame.payload) < _MEASUREMENTS_PAYLOAD_SIZE:
            raise DPS150ProtocolError("Measurement response is too short.")
        return Measurements(
            output_voltage=_read_float32(frame.payload, 0, "output voltage"),
            output_current=_read_float32(frame.payload, 4, "output current"),
            output_power=_read_float32(frame.payload, 8, "output power"),
        )

    def get_preset(self, slot: int) -> Preset:
        """Read stored voltage and current values without applying the preset.

        Args:
            slot: One-based preset slot from 1 through 6.

        Returns:
            :class:`~fnirsi_dps150.Preset` containing the stored values.

        Raises:
            ValueError: If ``slot`` is outside the supported range.
            :class:`~fnirsi_dps150.DPS150ProtocolError`: If either field is
                malformed or invalid.
            :class:`~fnirsi_dps150.DPS150ConnectionError`: If the device is not
                open.
            :class:`~fnirsi_dps150.DPS150CommunicationError`: If serial
                communication fails.
        """
        voltage_type, current_type = _preset_type_ids(slot)
        voltage_frame = self._transport.exchange(
            _ProtocolCommand.GET,
            voltage_type,
            b"",
            expected_response=(_ProtocolCommand.GET, voltage_type),
        )
        current_frame = self._transport.exchange(
            _ProtocolCommand.GET,
            current_type,
            b"",
            expected_response=(_ProtocolCommand.GET, current_type),
        )
        voltage = _read_float32(voltage_frame.payload, 0, "preset voltage")
        current = _read_float32(current_frame.payload, 0, "preset current")
        if voltage < 0 or current < 0:
            raise DPS150ProtocolError("Preset contains a negative value.")
        return Preset(voltage=voltage, current=current)

    def get_system_settings(self) -> SystemSettings:
        """Read verified brightness and metering settings.

        Volume, capacity, and energy are intentionally omitted because their
        semantics or write behavior have not been verified on the target unit.

        Returns:
            :class:`~fnirsi_dps150.SystemSettings` with brightness and metering
            state.

        Raises:
            :class:`~fnirsi_dps150.DPS150ProtocolError`: If either field is
                malformed or invalid.
            :class:`~fnirsi_dps150.DPS150ConnectionError`: If the device is not
                open.
            :class:`~fnirsi_dps150.DPS150CommunicationError`: If serial
                communication fails.
        """
        brightness_frame = self._transport.exchange(
            _ProtocolCommand.GET,
            _ProtocolType.BRIGHTNESS,
            b"",
            expected_response=(_ProtocolCommand.GET, _ProtocolType.BRIGHTNESS),
        )
        metering_frame = self._transport.exchange(
            _ProtocolCommand.GET,
            _ProtocolType.METERING_ENABLED,
            b"",
            expected_response=(
                _ProtocolCommand.GET,
                _ProtocolType.METERING_ENABLED,
            ),
        )
        if len(brightness_frame.payload) < 1:
            raise DPS150ProtocolError("Brightness response is too short.")
        if len(metering_frame.payload) < 1:
            raise DPS150ProtocolError("Metering response is too short.")

        brightness = brightness_frame.payload[0]
        metering_enabled = metering_frame.payload[0]
        if brightness > _BRIGHTNESS_MAX:
            raise DPS150ProtocolError("Device returned an invalid brightness level.")
        if metering_enabled not in (0, 1):
            raise DPS150ProtocolError("Device returned an invalid metering state.")
        return SystemSettings(
            brightness=brightness,
            metering_enabled=bool(metering_enabled),
        )

    def set_preset(self, slot: int, preset: Preset) -> None:
        """Write voltage and current values to a stored preset slot.

        This writes the native preset fields; it does not load them into the
        active setpoints. The two field writes are not atomic.

        Args:
            slot: One-based preset slot from 1 through 6.
            preset: :class:`~fnirsi_dps150.Preset` values to store.

        Raises:
            ValueError: If the slot or preset values are invalid or exceed the
                device-reported limits.
            :class:`~fnirsi_dps150.DPS150Error`: If output is enabled or serial
                status/communication fails.
        """
        voltage_type, current_type = _preset_type_ids(slot)
        if not isinstance(preset, Preset):
            raise ValueError("preset must be a Preset instance.")
        voltage, voltage_payload = _prepare_setpoint(preset.voltage, "voltage")
        current, current_payload = _prepare_setpoint(preset.current, "current")
        status = self._get_status_for_setting_write()
        if voltage > status.voltage_limit:
            raise ValueError(
                f"Preset voltage {voltage} V exceeds the device-reported limit "
                f"of {status.voltage_limit} V."
            )
        if current > status.current_limit:
            raise ValueError(
                f"Preset current {current} A exceeds the device-reported limit "
                f"of {status.current_limit} A."
            )
        self._transport.send(_ProtocolCommand.SET, voltage_type, voltage_payload)
        self._transport.send(_ProtocolCommand.SET, current_type, current_payload)

    def set_brightness(self, brightness: int) -> None:
        """Set the verified display brightness level.

        Args:
            brightness: Brightness level from 0 through 10.

        Raises:
            ValueError: If ``brightness`` is not an integer in the supported
                range.
            :class:`~fnirsi_dps150.DPS150Error`: If output is enabled, status
                cannot be read, or serial communication fails.
        """
        if (
            isinstance(brightness, bool)
            or not isinstance(brightness, int)
            or not _BRIGHTNESS_MIN <= brightness <= _BRIGHTNESS_MAX
        ):
            raise ValueError(
                f"brightness must be an integer from {_BRIGHTNESS_MIN} through "
                f"{_BRIGHTNESS_MAX}."
            )
        self._get_status_for_setting_write()
        self._transport.send(
            _ProtocolCommand.SET,
            _ProtocolType.BRIGHTNESS,
            bytes((brightness,)),
        )

    def set_metering_enabled(self, enabled: bool) -> None:
        """Enable or disable the verified metering setting.

        Args:
            enabled: ``True`` to enable metering, ``False`` to disable it.

        Raises:
            ValueError: If ``enabled`` is not a bool.
            :class:`~fnirsi_dps150.DPS150Error`: If output is enabled or serial
                status/communication fails.
        """
        if not isinstance(enabled, bool):
            raise ValueError("enabled must be a bool.")
        self._get_status_for_setting_write()
        self._transport.send(
            _ProtocolCommand.SET,
            _ProtocolType.METERING_ENABLED,
            bytes((int(enabled),)),
        )

    def set_voltage(self, voltage: float) -> None:
        """Set the output voltage without enabling output.

        Args:
            voltage: Non-negative setpoint in volts.

        Raises:
            ValueError: If the value is invalid or exceeds the reported limit.
            :class:`~fnirsi_dps150.DPS150Error`: If status read or serial
                communication fails.
        """
        value, payload = _prepare_setpoint(voltage, "voltage")
        status = self.get_status()
        if value > status.voltage_limit:
            raise ValueError(
                f"Voltage {value} V exceeds the device-reported limit "
                f"of {status.voltage_limit} V."
            )
        self._transport.send(
            _ProtocolCommand.SET,
            _ProtocolType.VOLTAGE_SETPOINT,
            payload,
        )

    def set_current(self, current: float) -> None:
        """Set the output current limit without enabling output.

        Args:
            current: Non-negative setpoint in amperes.

        Raises:
            ValueError: If the value is invalid or exceeds the reported limit.
            :class:`~fnirsi_dps150.DPS150Error`: If status read or serial
                communication fails.
        """
        value, payload = _prepare_setpoint(current, "current")
        status = self.get_status()
        if value > status.current_limit:
            raise ValueError(
                f"Current {value} A exceeds the device-reported limit "
                f"of {status.current_limit} A."
            )
        self._transport.send(
            _ProtocolCommand.SET,
            _ProtocolType.CURRENT_SETPOINT,
            payload,
        )

    def set_output(self, enabled: bool) -> None:
        """Send an explicit output-enable or output-disable command.

        The method does not read back the resulting state. Command/state
        readback was verified on COM64 without a load; loaded behavior and
        emergency-shutdown reliability were not verified.

        Args:
            enabled: ``True`` to enable output, ``False`` to disable it.

        Raises:
            ValueError: If ``enabled`` is not a bool.
            :class:`~fnirsi_dps150.DPS150Error`: If serial communication fails.
        """
        if not isinstance(enabled, bool):
            raise ValueError("enabled must be a bool.")
        self._transport.send(
            _ProtocolCommand.SET,
            _ProtocolType.OUTPUT,
            bytes((int(enabled),)),
        )

    def _get_status_for_setting_write(self) -> DeviceStatus:
        """Read status after requiring capability writes to be output-OFF.

        Returns:
            The current status with output disabled.

        Raises:
            :class:`~fnirsi_dps150.DPS150Error`: If output is enabled. Read
                failures are propagated from :meth:`get_status`.
        """
        status = self.get_status()
        if status.output_enabled:
            raise DPS150Error(
                "Preset and system-setting writes are only verified with output disabled."
            )
        return status

    def __enter__(self) -> DPS150:
        """Open this device for use in a ``with`` statement."""
        self.open()
        return self

    def __exit__(
        self,
        exception_type: type[BaseException] | None,
        exception: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        """Close the host serial port when leaving a ``with`` statement."""
        self.close()


def _preset_type_ids(slot: int) -> tuple[_ProtocolType, _ProtocolType]:
    """Map a one-based preset slot to its native voltage and current types.

    Args:
        slot: Preset slot from 1 through 6.

    Returns:
        Voltage and current protocol types for the slot.

    Raises:
        ValueError: If ``slot`` is not an integer from 1 through 6.
    """
    if (
        isinstance(slot, bool)
        or not isinstance(slot, int)
        or not _PRESET_SLOT_MIN <= slot <= _PRESET_SLOT_COUNT
    ):
        raise ValueError(
            f"slot must be an integer from {_PRESET_SLOT_MIN} through "
            f"{_PRESET_SLOT_COUNT}."
        )
    voltage_type = int(_ProtocolType.PRESET_1_VOLTAGE) + 2 * (slot - 1)
    return _ProtocolType(voltage_type), _ProtocolType(voltage_type + 1)


def _read_float32(payload: bytes, offset: int, field_name: str) -> float:
    if len(payload) < offset + 4:
        raise DPS150ProtocolError(f"Response is missing {field_name}.")
    value = struct.unpack_from("<f", payload, offset)[0]
    if not math.isfinite(value):
        raise DPS150ProtocolError(f"Device returned a non-finite {field_name}.")
    return value


def _prepare_setpoint(value: float, field_name: str) -> tuple[float, bytes]:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{field_name} must be a finite non-negative number.")
    try:
        numeric_value = float(value)
    except OverflowError as error:
        raise ValueError(
            f"{field_name} must be a finite non-negative number."
        ) from error
    if not math.isfinite(numeric_value) or numeric_value < 0:
        raise ValueError(f"{field_name} must be a finite non-negative number.")

    try:
        payload = struct.pack("<f", numeric_value)
    except (OverflowError, struct.error) as error:
        raise ValueError(f"{field_name} is outside the float32 range.") from error
    encoded_value = struct.unpack("<f", payload)[0]
    if not math.isfinite(encoded_value) or numeric_value > 0 and encoded_value == 0:
        raise ValueError(f"{field_name} is outside the float32 range.")
    return encoded_value, payload
