"""Public synchronous device interface."""

from __future__ import annotations

import math
import struct
from types import TracebackType
from typing import Final

from ._protocol import _Frame
from ._transport import _SerialTransport
from .definitions.exceptions import DPS150Error, DPS150ProtocolError
from .models import DeviceStatus, Measurements

_GET_COMMAND: Final[int] = 0xA1
_SET_COMMAND: Final[int] = 0xB1
_CONNECT_COMMAND: Final[int] = 0xC1
_SESSION_TYPE: Final[int] = 0x00
_STATUS_TYPE: Final[int] = 0xFF
_MEASUREMENTS_TYPE: Final[int] = 195
_VOLTAGE_SETPOINT_TYPE: Final[int] = 193
_CURRENT_SETPOINT_TYPE: Final[int] = 194
_OUTPUT_TYPE: Final[int] = 219
_OUTPUT_ENABLED_OFFSET: Final[int] = 107
_VOLTAGE_SETPOINT_OFFSET: Final[int] = 4
_CURRENT_SETPOINT_OFFSET: Final[int] = 8
_VOLTAGE_LIMIT_OFFSET: Final[int] = 111
_CURRENT_LIMIT_OFFSET: Final[int] = 115
_STATUS_PAYLOAD_SIZE: Final[int] = 119
_MEASUREMENTS_PAYLOAD_SIZE: Final[int] = 12


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
            self._transport.send(_CONNECT_COMMAND, _SESSION_TYPE, b"\x01")
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
        frame = self._request(
            _GET_COMMAND,
            _STATUS_TYPE,
            b"",
            expected_response=(_GET_COMMAND, _STATUS_TYPE),
        )
        if len(frame.payload) < _STATUS_PAYLOAD_SIZE:
            raise DPS150ProtocolError("Status response is too short.")

        output_enabled = frame.payload[_OUTPUT_ENABLED_OFFSET]
        if output_enabled not in (0, 1):
            raise DPS150ProtocolError("Status contains an invalid output state.")
        voltage_limit = _read_float32(
            frame.payload,
            _VOLTAGE_LIMIT_OFFSET,
            "voltage limit",
        )
        current_limit = _read_float32(
            frame.payload,
            _CURRENT_LIMIT_OFFSET,
            "current limit",
        )
        if voltage_limit < 0 or current_limit < 0:
            raise DPS150ProtocolError("Status contains a negative device limit.")
        return DeviceStatus(
            set_voltage=_read_float32(
                frame.payload,
                _VOLTAGE_SETPOINT_OFFSET,
                "voltage setpoint",
            ),
            set_current=_read_float32(
                frame.payload,
                _CURRENT_SETPOINT_OFFSET,
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
        frame = self._request(
            _GET_COMMAND,
            _MEASUREMENTS_TYPE,
            b"",
            expected_response=(_GET_COMMAND, _MEASUREMENTS_TYPE),
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
        self._transport.send(_SET_COMMAND, _VOLTAGE_SETPOINT_TYPE, payload)

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
        self._transport.send(_SET_COMMAND, _CURRENT_SETPOINT_TYPE, payload)

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
        self._transport.send(_SET_COMMAND, _OUTPUT_TYPE, bytes((int(enabled),)))

    def _request(
        self,
        command: int,
        type_id: int,
        payload: bytes = b"",
        expected_response: tuple[int, int] | None = None,
    ) -> _Frame:
        """Send one private frame and wait for its response.

        Args:
            command: Protocol command byte.
            type_id: Protocol data type byte.
            payload: Request data.
            expected_response: Optional command/type pair to match.

        Returns:
            The decoded response frame.
        """
        return self._transport.exchange(
            command,
            type_id,
            payload,
            expected_response=expected_response,
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
