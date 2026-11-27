"""Private DPS150 serial-frame codec."""

from dataclasses import dataclass
from typing import Final

from .definitions.exceptions import DPS150ProtocolError

_REQUEST_HEADER: Final[int] = 0xF1
_RESPONSE_HEADER: Final[int] = 0xF0
_MAX_PAYLOAD_SIZE: Final[int] = 0xFF


@dataclass(frozen=True, slots=True)
class _Frame:
    """Decoded protocol frame.

    Attributes:
        command: Command byte from the frame.
        type_id: Data type byte from the frame.
        payload: Frame data bytes.
    """

    command: int
    type_id: int
    payload: bytes


def _encode_frame(
    command: int,
    type_id: int,
    payload: bytes = b"",
    header: int = _REQUEST_HEADER,
) -> bytes:
    """Encode one private request or response frame."""
    if not 0 <= command <= 0xFF or isinstance(command, bool):
        raise DPS150ProtocolError("Frame command must be an unsigned byte.")
    if not 0 <= type_id <= 0xFF or isinstance(type_id, bool):
        raise DPS150ProtocolError("Frame type must be an unsigned byte.")
    if header not in (_REQUEST_HEADER, _RESPONSE_HEADER):
        raise DPS150ProtocolError("Frame header is not supported.")
    if len(payload) > _MAX_PAYLOAD_SIZE:
        raise DPS150ProtocolError("Frame payload exceeds 255 bytes.")

    payload_length = len(payload)
    checksum = (type_id + payload_length + sum(payload)) & 0xFF
    return bytes((header, command, type_id, payload_length)) + payload + bytes(
        (checksum,)
    )


def _decode_frame(packet: bytes) -> _Frame:
    """Validate and decode one complete response frame."""
    if len(packet) < 5:
        raise DPS150ProtocolError("Frame is shorter than its header and checksum.")
    if packet[0] != _RESPONSE_HEADER:
        raise DPS150ProtocolError("Frame has an invalid response header.")

    payload_length = packet[3]
    if len(packet) != payload_length + 5:
        raise DPS150ProtocolError("Frame length does not match its payload length.")

    payload = packet[4:-1]
    expected_checksum = (packet[2] + payload_length + sum(payload)) & 0xFF
    if packet[-1] != expected_checksum:
        raise DPS150ProtocolError("Frame checksum does not match.")

    return _Frame(command=packet[1], type_id=packet[2], payload=payload)
