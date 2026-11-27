"""Synchronous controls for the FNIRSI DPS150 power supply."""

from typing import Final

from .definitions.exceptions import (
    DPS150CommunicationError,
    DPS150ConnectionError,
    DPS150Error,
    DPS150ProtocolError,
    DPS150TimeoutError,
)
from .definitions.namespace import ProtectionStatus, RegulationMode
from .device import DPS150, find_ports
from .models import (
    DeviceInfo,
    DeviceSnapshot,
    DeviceStatus,
    Measurements,
    MeteringReadings,
    Preset,
    ProtectionLimits,
    ProtectionSettings,
    SystemSettings,
)

__version__: Final[str] = "0.1.0"

__all__ = [
    "__version__",
    "DPS150",
    "find_ports",
    "DeviceInfo",
    "DeviceSnapshot",
    "DeviceStatus",
    "Measurements",
    "MeteringReadings",
    "Preset",
    "ProtectionLimits",
    "ProtectionSettings",
    "ProtectionStatus",
    "RegulationMode",
    "SystemSettings",
    "DPS150Error",
    "DPS150CommunicationError",
    "DPS150ConnectionError",
    "DPS150ProtocolError",
    "DPS150TimeoutError",
]
