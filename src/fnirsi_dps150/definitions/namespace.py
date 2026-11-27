"""DPS150 protocol identifiers and domain enums."""

from enum import IntEnum
from typing import Final

_PRESET_SLOT_MIN: Final[int] = 1
_PRESET_SLOT_COUNT: Final[int] = 6
_BRIGHTNESS_MIN: Final[int] = 0
_BRIGHTNESS_MAX: Final[int] = 14
_VOLUME_MIN: Final[int] = 0
_VOLUME_MAX: Final[int] = 10
_USB_VID: Final[int] = 0x2E3C
_USB_PID: Final[int] = 0x5740


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


class RegulationMode(IntEnum):
    """Device operating modes.

    Attributes:
        CC: Constant-current regulation.
        CV: Constant-voltage regulation.
    """

    CC = 0
    CV = 1


class ProtectionStatus(IntEnum):
    """Target-verified protection status codes reported by the DPS150.

    Attributes:
        NONE: No protection trip is active.
        OVP: Over-voltage protection tripped.
        OCP: Over-current protection tripped.
        OPP: Over-power protection tripped.
        OTP: Over-temperature protection tripped.
        LVP: Low input-voltage protection tripped.
    """

    NONE = 0
    OVP = 1
    OCP = 2
    OPP = 3
    OTP = 4
    LVP = 5


class _ProtocolType(IntEnum):
    """Data type bytes used by the private DPS150 protocol.

    Attributes:
        SESSION: Session-connect payload type.
        STATUS: Device status snapshot type.
        INPUT_VOLTAGE: Device input voltage type.
        VOLTAGE_SETPOINT: Output voltage setpoint type.
        CURRENT_SETPOINT: Output current setpoint type.
        MEASUREMENTS: Output measurements type.
        TEMPERATURE: Device temperature type.
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
        OVER_VOLTAGE_PROTECTION: Over-voltage protection threshold type.
        OVER_CURRENT_PROTECTION: Over-current protection threshold type.
        OVER_POWER_PROTECTION: Over-power protection threshold type.
        OVER_TEMPERATURE_PROTECTION: Over-temperature protection threshold type.
        LOW_VOLTAGE_PROTECTION: Low-voltage protection threshold type.
        PROTECTION_STATUS: Device-reported protection status byte type.
        REGULATION_MODE: Constant-current/constant-voltage mode type.
        BRIGHTNESS: Display brightness type.
        VOLUME: Buzzer volume type.
        METERING_ENABLED: Metering enable type.
        OUTPUT_CAPACITY: Accumulated output capacity (Ah) type.
        OUTPUT_ENERGY: Accumulated output energy (Wh) type.
        MODEL: Device model type.
        HARDWARE_VERSION: Hardware version type.
        FIRMWARE_VERSION: Firmware version type.
        OVER_VOLTAGE_LIMIT: Device-reported OVP ceiling type.
        OVER_CURRENT_LIMIT: Device-reported OCP ceiling type.
        OVER_POWER_LIMIT: Device-reported OPP ceiling type.
        OVER_TEMPERATURE_LIMIT: Device-reported OTP ceiling type.
        LOW_VOLTAGE_LIMIT: Device-reported LVP ceiling type.
    """

    SESSION = 0x00
    STATUS = 0xFF
    INPUT_VOLTAGE = 192
    VOLTAGE_SETPOINT = 193
    CURRENT_SETPOINT = 194
    MEASUREMENTS = 195
    TEMPERATURE = 196
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
    OVER_VOLTAGE_PROTECTION = 209
    OVER_CURRENT_PROTECTION = 210
    OVER_POWER_PROTECTION = 211
    OVER_TEMPERATURE_PROTECTION = 212
    LOW_VOLTAGE_PROTECTION = 213
    BRIGHTNESS = 214
    VOLUME = 215
    METERING_ENABLED = 216
    OUTPUT_CAPACITY = 217
    OUTPUT_ENERGY = 218
    OUTPUT = 219
    PROTECTION_STATUS = 220
    REGULATION_MODE = 221
    MODEL = 222
    HARDWARE_VERSION = 223
    FIRMWARE_VERSION = 224
    OVER_VOLTAGE_LIMIT = 228
    OVER_CURRENT_LIMIT = 229
    OVER_POWER_LIMIT = 230
    OVER_TEMPERATURE_LIMIT = 231
    LOW_VOLTAGE_LIMIT = 232


class _StatusOffset(IntEnum):
    """Byte offsets of fields in the device status payload.

    Attributes:
        INPUT_VOLTAGE: Start of the measured input voltage.
        VOLTAGE_SETPOINT: Start of the voltage setpoint.
        CURRENT_SETPOINT: Start of the current setpoint.
        OUTPUT_VOLTAGE: Start of the measured output voltage.
        OUTPUT_CURRENT: Start of the measured output current.
        OUTPUT_POWER: Start of the measured output power.
        TEMPERATURE: Start of the device temperature.
        PRESETS_START: Start of the six preset voltage/current pairs.
        OVER_VOLTAGE_PROTECTION: Start of the OVP threshold.
        OVER_CURRENT_PROTECTION: Start of the OCP threshold.
        OVER_POWER_PROTECTION: Start of the OPP threshold.
        OVER_TEMPERATURE_PROTECTION: Start of the OTP threshold.
        LOW_VOLTAGE_PROTECTION: Start of the LVP threshold.
        BRIGHTNESS: Display brightness byte.
        VOLUME: Buzzer volume byte.
        METERING_ENABLED: Metering enable byte.
        OUTPUT_CAPACITY: Start of the accumulated output capacity (Ah).
        OUTPUT_ENERGY: Start of the accumulated output energy (Wh).
        OUTPUT_ENABLED: Output state byte.
        PROTECTION_STATUS: Protection status byte.
        REGULATION_MODE: Regulation mode byte.
        VOLTAGE_LIMIT: Start of the reported voltage limit.
        CURRENT_LIMIT: Start of the reported current limit.
        OVER_VOLTAGE_LIMIT: Start of the reported OVP ceiling.
        OVER_CURRENT_LIMIT: Start of the reported OCP ceiling.
        OVER_POWER_LIMIT: Start of the reported OPP ceiling.
        OVER_TEMPERATURE_LIMIT: Start of the reported OTP ceiling.
        LOW_VOLTAGE_LIMIT: Start of the reported LVP ceiling.
    """

    INPUT_VOLTAGE = 0
    VOLTAGE_SETPOINT = 4
    CURRENT_SETPOINT = 8
    OUTPUT_VOLTAGE = 12
    OUTPUT_CURRENT = 16
    OUTPUT_POWER = 20
    TEMPERATURE = 24
    PRESETS_START = 28
    OVER_VOLTAGE_PROTECTION = 76
    OVER_CURRENT_PROTECTION = 80
    OVER_POWER_PROTECTION = 84
    OVER_TEMPERATURE_PROTECTION = 88
    LOW_VOLTAGE_PROTECTION = 92
    BRIGHTNESS = 96
    VOLUME = 97
    METERING_ENABLED = 98
    OUTPUT_CAPACITY = 99
    OUTPUT_ENERGY = 103
    OUTPUT_ENABLED = 107
    PROTECTION_STATUS = 108
    REGULATION_MODE = 109
    VOLTAGE_LIMIT = 111
    CURRENT_LIMIT = 115
    OVER_VOLTAGE_LIMIT = 119
    OVER_CURRENT_LIMIT = 123
    OVER_POWER_LIMIT = 127
    OVER_TEMPERATURE_LIMIT = 131
    LOW_VOLTAGE_LIMIT = 135


_STATUS_PAYLOAD_SIZE: Final[int] = 119
_FULL_STATUS_PAYLOAD_SIZE: Final[int] = 139
_MEASUREMENTS_PAYLOAD_SIZE: Final[int] = 12
