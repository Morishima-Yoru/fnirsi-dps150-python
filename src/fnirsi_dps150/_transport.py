"""Private synchronous serial transport for DPS150 protocol frames."""

from __future__ import annotations

import time
from typing import Final

import serial

from ._protocol import _RESPONSE_HEADER, _Frame, _decode_frame, _encode_frame
from .definitions.exceptions import (
    DPS150CommunicationError,
    DPS150ConnectionError,
    DPS150ProtocolError,
    DPS150TimeoutError,
)

_BAUDRATE: Final[int] = 115200
_RESPONSE_HEADER_SIZE: Final[int] = 4


class _SerialTransport:
    """Own a serial port and exchange one request with one response.

    Attributes:
        _port: Host serial port name.
        _timeout: Maximum time in seconds to receive a complete frame.
        _serial: Open pySerial connection, if any.
    """

    def __init__(self, port: str, timeout: float) -> None:
        """Store connection settings without opening the serial port."""
        self._port = port
        self._timeout = timeout
        self._serial: serial.SerialBase | None = None

    def open(self) -> bool:
        """Open the serial port and report whether a new port was created.

        Returns:
            ``True`` if this call opened the port, otherwise ``False``.

        Raises:
            :class:`~fnirsi_dps150.DPS150CommunicationError`: If opening fails.
        """
        if self._serial is not None and self._serial.is_open:
            return False

        try:
            self._serial = serial.Serial(
                port=self._port,
                baudrate=_BAUDRATE,
                bytesize=serial.EIGHTBITS,
                parity=serial.PARITY_NONE,
                stopbits=serial.STOPBITS_ONE,
                timeout=self._timeout,
                write_timeout=self._timeout,
                xonxoff=False,
                rtscts=False,
                dsrdtr=False,
            )
        except (serial.SerialException, OSError) as error:
            raise DPS150CommunicationError(
                f"Could not open serial port {self._port!r}."
            ) from error
        return True

    def close(self) -> None:
        """Close the serial port without sending a device command."""
        if self._serial is None:
            return

        try:
            self._serial.close()
        except (serial.SerialException, OSError) as error:
            raise DPS150CommunicationError(
                f"Could not close serial port {self._port!r}."
            ) from error
        self._serial = None

    def send(self, command: int, type_id: int, payload: bytes) -> None:
        """Write one frame without waiting for a response."""
        serial_port = self._serial
        if serial_port is None or not serial_port.is_open:
            raise DPS150ConnectionError("Open the device before sending a request.")

        self._write_frame(serial_port, command, type_id, payload)

    def exchange(
        self,
        command: int,
        type_id: int,
        payload: bytes,
        expected_response: tuple[int, int] | None = None,
    ) -> _Frame:
        """Write once and read until the expected frame or one deadline.

        Valid frames that do not match ``expected_response`` are consumed while
        waiting for the requested frame. No request is retried.
        """
        serial_port = self._serial
        if serial_port is None or not serial_port.is_open:
            raise DPS150ConnectionError("Open the device before sending a request.")

        self._write_frame(serial_port, command, type_id, payload)
        deadline = time.monotonic() + self._timeout
        while True:
            frame = self._read_frame(serial_port, deadline)
            response_id = (frame.command, frame.type_id)
            if expected_response is None or response_id == expected_response:
                return frame

    def _write_frame(
        self,
        serial_port: serial.SerialBase,
        command: int,
        type_id: int,
        payload: bytes,
    ) -> None:
        """Encode and write one frame, reporting short writes explicitly."""
        packet = _encode_frame(command, type_id, payload)
        try:
            written = serial_port.write(packet)
            if written != len(packet):
                raise DPS150CommunicationError(
                    "The serial port did not accept the complete request frame."
                )
        except (serial.SerialException, OSError) as error:
            raise DPS150CommunicationError(
                "Serial communication with the DPS150 failed."
            ) from error

    def _read_frame(
        self,
        serial_port: serial.SerialBase,
        deadline: float,
    ) -> _Frame:
        """Read and validate one response before the configured deadline."""
        header = self._read_exact(serial_port, _RESPONSE_HEADER_SIZE, deadline)
        if header[0] != _RESPONSE_HEADER:
            raise DPS150ProtocolError("Frame has an invalid response header.")

        payload_length = header[3]
        tail = self._read_exact(serial_port, payload_length + 1, deadline)
        return _decode_frame(header + tail)

    def _read_exact(
        self,
        serial_port: serial.SerialBase,
        count: int,
        deadline: float,
    ) -> bytes:
        """Read exactly ``count`` bytes before the frame deadline.

        Args:
            serial_port: The connected serial port.
            count: Number of bytes to read.
            deadline: Monotonic deadline for the current response frame.

        Returns:
            The requested bytes.

        Raises:
            :class:`~fnirsi_dps150.DPS150TimeoutError`: If the deadline expires.
        """
        result = bytearray()
        while len(result) < count:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise DPS150TimeoutError("Timed out while reading a response frame.")

            serial_port.timeout = remaining
            try:
                chunk = serial_port.read(count - len(result))
            finally:
                serial_port.timeout = self._timeout

            if not chunk:
                raise DPS150TimeoutError("Timed out while reading a response frame.")
            result.extend(chunk)
        return bytes(result)
