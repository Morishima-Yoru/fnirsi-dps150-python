"""Private protocol identifiers and payload layout for the DPS150."""

from enum import IntEnum
from typing import Final


class _ProtocolCommand(IntEnum):
    """Command bytes used by the private DPS150 protocol.

    Attributes:
        GET: Read data from the device.
        SET: Write data to the device.
        CONNECT: Establish a device session.
    """

    GET = 0xA1
    SET = 0xB1
    CONNECT = 0xC1


class _ProtocolType(IntEnum):
    """Data type bytes used by the private DPS150 protocol.

    Attributes:
        SESSION: Session-connect payload type.
        STATUS: Device status snapshot type.
        MEASUREMENTS: Output measurements type.
        VOLTAGE_SETPOINT: Voltage setpoint type.
        CURRENT_SETPOINT: Current setpoint type.
        OUTPUT: Output-enable state type.
    """

    SESSION = 0x00
    STATUS = 0xFF
    MEASUREMENTS = 195
    VOLTAGE_SETPOINT = 193
    CURRENT_SETPOINT = 194
    OUTPUT = 219


class _StatusOffset(IntEnum):
    """Byte offsets of fields in the device status payload.

    Attributes:
        VOLTAGE_SETPOINT: Start of the voltage setpoint.
        CURRENT_SETPOINT: Start of the current setpoint.
        OUTPUT_ENABLED: Output state byte.
        VOLTAGE_LIMIT: Start of the reported voltage limit.
        CURRENT_LIMIT: Start of the reported current limit.
    """

    VOLTAGE_SETPOINT = 4
    CURRENT_SETPOINT = 8
    OUTPUT_ENABLED = 107
    VOLTAGE_LIMIT = 111
    CURRENT_LIMIT = 115


_STATUS_PAYLOAD_SIZE: Final[int] = 119
_MEASUREMENTS_PAYLOAD_SIZE: Final[int] = 12
