"""Public synchronous device interface."""

from __future__ import annotations

import math
from types import TracebackType
from typing import Final

from ._protocol import _Frame
from ._transport import _SerialTransport
from .definitions.exceptions import DPS150Error, DPS150ProtocolError
from .models import DeviceStatus

_GET_COMMAND: Final[int] = 0xA1
_CONNECT_COMMAND: Final[int] = 0xC1
_SESSION_TYPE: Final[int] = 0x00
_STATUS_TYPE: Final[int] = 0xFF
_OUTPUT_ENABLED_OFFSET: Final[int] = 107


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
        """Read the device output state synchronously.

        Returns:
            A typed status snapshot containing the reported output state.

        Raises:
            :class:`~fnirsi_dps150.DPS150ProtocolError`: If the response is
                malformed or incomplete.
            :class:`~fnirsi_dps150.DPS150ConnectionError`: If the device is not
                open.
            :class:`~fnirsi_dps150.DPS150CommunicationError`: If serial
                communication fails.
        """
        frame = self._request(_GET_COMMAND, _STATUS_TYPE, b"")
        if frame.command != _GET_COMMAND or frame.type_id != _STATUS_TYPE:
            raise DPS150ProtocolError("Received an unexpected status response.")
        if len(frame.payload) <= _OUTPUT_ENABLED_OFFSET:
            raise DPS150ProtocolError("Status response is too short.")

        output_enabled = frame.payload[_OUTPUT_ENABLED_OFFSET]
        if output_enabled not in (0, 1):
            raise DPS150ProtocolError("Status contains an invalid output state.")
        return DeviceStatus(output_enabled=bool(output_enabled))

    def _request(self, command: int, type_id: int, payload: bytes = b"") -> _Frame:
        """Send one private frame and wait for its response.

        Args:
            command: Protocol command byte.
            type_id: Protocol data type byte.
            payload: Request data.

        Returns:
            The decoded response frame.
        """
        return self._transport.exchange(command, type_id, payload)

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
