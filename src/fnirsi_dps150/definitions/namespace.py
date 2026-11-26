"""Private protocol identifiers and payload layout for the DPS150."""

from enum import IntEnum
from typing import Final

_PRESET_SLOT_MIN: Final[int] = 1
_PRESET_SLOT_COUNT: Final[int] = 6
_BRIGHTNESS_MIN: Final[int] = 0
_BRIGHTNESS_MAX: Final[int] = 10


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
        PRESET_1_VOLTAGE: Preset slot 1 voltage type.
        PRESET_1_CURRENT: Preset slot 1 current type.
        PRESET_2_VOLTAGE: Preset slot 2 voltage type.
        PRESET_2_CURRENT: Preset slot 2 current type.
        PRESET_3_VOLTAGE: Preset slot 3 voltage type.
        PRESET_3_CURRENT: Preset slot 3 current type.
        PRESET_4_VOLTAGE: Preset slot 4 voltage type.
        PRESET_4_CURRENT: Preset slot 4 current type.
        PRESET_5_VOLTAGE: Preset slot 5 voltage type.
        PRESET_5_CURRENT: Preset slot 5 current type.
        PRESET_6_VOLTAGE: Preset slot 6 voltage type.
        PRESET_6_CURRENT: Preset slot 6 current type.
        BRIGHTNESS: Display brightness type.
        METERING_ENABLED: Metering enable type.
    """

    SESSION = 0x00
    STATUS = 0xFF
    MEASUREMENTS = 195
    VOLTAGE_SETPOINT = 193
    CURRENT_SETPOINT = 194
    PRESET_1_VOLTAGE = 197
    PRESET_1_CURRENT = 198
    PRESET_2_VOLTAGE = 199
    PRESET_2_CURRENT = 200
    PRESET_3_VOLTAGE = 201
    PRESET_3_CURRENT = 202
    PRESET_4_VOLTAGE = 203
    PRESET_4_CURRENT = 204
    PRESET_5_VOLTAGE = 205
    PRESET_5_CURRENT = 206
    PRESET_6_VOLTAGE = 207
    PRESET_6_CURRENT = 208
    BRIGHTNESS = 214
    METERING_ENABLED = 216
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
