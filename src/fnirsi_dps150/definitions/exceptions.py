"""Exceptions raised by the FNIRSI DPS150 library."""


class DPS150Error(Exception):
    """Base exception for errors raised by this library."""


class DPS150CommunicationError(DPS150Error):
    """Raised when serial communication with the device fails."""


class DPS150ConnectionError(DPS150Error):
    """Raised when a serial operation is attempted while disconnected."""


class DPS150ProtocolError(DPS150Error):
    """Raised when a received or constructed protocol frame is invalid."""


class DPS150TimeoutError(DPS150CommunicationError):
    """Raised when a complete response frame is not received before timeout."""
