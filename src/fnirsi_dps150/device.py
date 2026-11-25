"""Public synchronous device interface."""

from __future__ import annotations

import math
import struct
from types import TracebackType

from ._transport import _SerialTransport
from .definitions.exceptions import DPS150Error, DPS150ProtocolError
from .definitions.namespace import (
    _MEASUREMENTS_PAYLOAD_SIZE,
    _STATUS_PAYLOAD_SIZE,
    _ProtocolCommand,
    _ProtocolType,
    _StatusOffset,
)
from .models import DeviceStatus, Measurements


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

        The method does not read back the resulting state. Target-side behavior
        for this command has not been verified on the test unit.

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
