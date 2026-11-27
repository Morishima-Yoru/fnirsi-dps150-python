"""Public synchronous device interface."""

from __future__ import annotations

import contextlib
import math
import re
import struct
from types import TracebackType
from typing import Final

import serial.tools.list_ports

from ._transport import _SerialTransport
from .definitions.exceptions import (
    DPS150ConnectionError,
    DPS150Error,
    DPS150ProtocolError,
)
from .definitions.namespace import (
    _BRIGHTNESS_MAX,
    _BRIGHTNESS_MIN,
    _FULL_STATUS_PAYLOAD_SIZE,
    _MEASUREMENTS_PAYLOAD_SIZE,
    _PRESET_SLOT_COUNT,
    _PRESET_SLOT_MIN,
    _STATUS_PAYLOAD_SIZE,
    _USB_PID,
    _USB_VID,
    _VOLUME_MAX,
    _VOLUME_MIN,
    _ProtocolCommand,
    _ProtocolType,
    ProtectionStatus,
    RegulationMode,
    _StatusOffset,
)
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


_HWID_VID_PATTERN: Final[re.Pattern[str]] = re.compile(
    r"VID(?::PID=|_)([0-9A-Fa-f]{4})",
    re.IGNORECASE,
)
_HWID_SER_PATTERN: Final[re.Pattern[str]] = re.compile(
    r"(?:^|\s)SER=([^\s]+)",
    re.IGNORECASE,
)


def find_ports() -> tuple[str, ...]:
    """Discover host serial ports matching the DPS150 USB VID and PID.

    Performs port metadata enumeration only and does not open any serial port.

    Returns:
        Sorted tuple of matching serial port names (for example, ``('COM64',)``).
    """
    return tuple(
        sorted(
            port.device
            for port in serial.tools.list_ports.comports()
            if port.vid == _USB_VID and port.pid == _USB_PID
        )
    )


def _port_has_usb_vid(port_info: object, target_vid: int) -> bool:
    """Return whether enumerated port metadata matches ``target_vid``."""
    vid = getattr(port_info, "vid", None)
    if isinstance(vid, int) and not isinstance(vid, bool):
        return vid == target_vid
    hwid = getattr(port_info, "hwid", None)
    if isinstance(hwid, str):
        match = _HWID_VID_PATTERN.search(hwid)
        if match is not None:
            return int(match.group(1), 16) == target_vid
    return False


def _port_serial_number(port_info: object) -> str | None:
    """Extract a stripped USB VCP serial number from port metadata if present."""
    raw_serial = getattr(port_info, "serial_number", None)
    if isinstance(raw_serial, str) and raw_serial.strip():
        return raw_serial.strip()
    hwid = getattr(port_info, "hwid", None)
    if isinstance(hwid, str):
        match = _HWID_SER_PATTERN.search(hwid)
        if match is not None and match.group(1).strip():
            return match.group(1).strip()
    return None


def _resolve_port_by_serial_number(serial_number: str) -> tuple[str, str]:
    """Resolve one USB VCP port among ``VID=0x2E3C`` devices by serial number.

    Args:
        serial_number: USB VCP serial number to match case-insensitively.

    Returns:
        Pair of ``(device_port, matched_serial_number)``.

    Raises:
        ValueError: If ``serial_number`` is not a non-empty string.
        :class:`~fnirsi_dps150.DPS150ConnectionError`: If zero or multiple
            matching USB ``VID=0x2E3C`` ports are found.
    """
    if not isinstance(serial_number, str) or not serial_number.strip():
        raise ValueError("serial_number must be a non-empty string.")
    normalized = serial_number.strip()
    target_key = normalized.casefold()
    matches: list[tuple[str, str]] = []
    for port_info in serial.tools.list_ports.comports():
        if not _port_has_usb_vid(port_info, _USB_VID):
            continue
        candidate_serial = _port_serial_number(port_info)
        if candidate_serial is None or candidate_serial.casefold() != target_key:
            continue
        device_name = getattr(port_info, "device", None)
        if isinstance(device_name, str) and device_name.strip():
            matches.append((device_name, candidate_serial))
    matches.sort(key=lambda item: item[0])
    if not matches:
        raise DPS150ConnectionError(
            f"No DPS150 device with USB VID 0x{_USB_VID:04X} and serial number "
            f"{normalized!r} was found."
        )
    if len(matches) > 1:
        ports_list = ", ".join(device_name for device_name, _ in matches)
        raise DPS150ConnectionError(
            f"Multiple USB VID 0x{_USB_VID:04X} ports match serial number "
            f"{normalized!r}: {ports_list}."
        )
    return matches[0]


class DPS150:
    """Control one FNIRSI DPS150 over its USB virtual serial port.

    Construction stores connection settings only. It does not open the port or
    send a command to the device.
    """

    def __init__(
        self,
        port: str | None = None,
        timeout: float = 1.0,
        *,
        serial_number: str | None = None,
    ) -> None:
        """Create a device handle without performing serial I/O.

        Provide either a host ``port`` or a USB VCP ``serial_number``. When
        ``serial_number`` is used, host port metadata matching USB VID
        ``0x2E3C`` is inspected without opening any serial port.

        Args:
            port: Host serial port, such as ``COM3``. Mutually exclusive with
                ``serial_number``.
            timeout: Finite positive timeout in seconds for serial I/O.
            serial_number: USB VCP serial number (for example,
                ``"10F5D04E4486"``) matched case-insensitively across USB VID
                ``0x2E3C`` ports. Mutually exclusive with ``port``.

        Raises:
            ValueError: If neither or both selectors are provided, or if
                ``port``, ``serial_number``, or ``timeout`` is invalid.
            :class:`~fnirsi_dps150.DPS150ConnectionError`: If
                ``serial_number`` matches zero or multiple USB VID ``0x2E3C``
                ports.
        """
        if port is not None and serial_number is not None:
            raise ValueError("Specify either port or serial_number, not both.")
        if port is None and serial_number is None:
            raise ValueError("Specify either port or serial_number.")
        if isinstance(timeout, bool) or not isinstance(timeout, (int, float)):
            raise ValueError("timeout must be a finite positive number.")
        try:
            timeout_seconds = float(timeout)
        except OverflowError as error:
            raise ValueError("timeout must be a finite positive number.") from error
        if not math.isfinite(timeout_seconds) or timeout_seconds <= 0:
            raise ValueError("timeout must be a finite positive number.")

        if port is not None:
            if not isinstance(port, str) or not port.strip():
                raise ValueError("port must be a non-empty string.")
            resolved_port = port
            resolved_serial_number: str | None = None
        else:
            assert serial_number is not None
            resolved_port, resolved_serial_number = _resolve_port_by_serial_number(
                serial_number
            )

        self._serial_number: str | None = resolved_serial_number
        self._transport = _SerialTransport(port=resolved_port, timeout=timeout_seconds)

    @property
    def port(self) -> str:
        """Return the configured host serial port name."""
        return self._transport.port

    @property
    def serial_number(self) -> str | None:
        """Return the matched USB VCP serial number, or ``None`` if opened by port."""
        return self._serial_number

    @property
    def timeout(self) -> float:
        """Return the configured serial I/O timeout in seconds."""
        return self._transport.timeout

    @property
    def is_open(self) -> bool:
        """Return whether the underlying serial connection is currently open."""
        return self._transport.is_open

    def __repr__(self) -> str:
        """Return a developer-friendly representation without doing I/O."""
        if self._serial_number is not None:
            return (
                f"DPS150(port={self.port!r}, "
                f"serial_number={self._serial_number!r}, "
                f"timeout={self.timeout!r}, "
                f"is_open={self.is_open!r})"
            )
        return (
            f"DPS150(port={self.port!r}, "
            f"timeout={self.timeout!r}, "
            f"is_open={self.is_open!r})"
        )

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
            with contextlib.suppress(DPS150Error):
                self._transport.close()
            raise

    def close(self, *, keep_locked: bool = False) -> None:
        """Close the host serial port, optionally leaving the front panel locked.

        By default this sends the session-disconnect command (``C1 00 00``)
        before closing the serial port, which releases the front-panel lock and
        stops unsolicited device telemetry without altering output state.

        Args:
            keep_locked: If ``True``, close the host port without sending the
                session-disconnect command.

        Raises:
            ValueError: If ``keep_locked`` is not a bool.
            :class:`~fnirsi_dps150.DPS150CommunicationError`: If sending the
                disconnect frame or closing the serial port fails.
        """
        if not isinstance(keep_locked, bool):
            raise ValueError("keep_locked must be a bool.")
        if not self._transport.is_open:
            return
        try:
            if not keep_locked:
                self._transport.send(
                    _ProtocolCommand.CONNECT,
                    _ProtocolType.SESSION,
                    b"\x00",
                )
                self._transport.wait_for_command_gap()
        finally:
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
        return _parse_device_status(self._get_status_payload())

    def get_snapshot(self) -> DeviceSnapshot:
        """Read the full device state snapshot from ``GET 0xFF``.

        Returns:
            A :class:`DeviceSnapshot` populated with all verified fields from the
            response payload. ``protection_limits`` is ``None`` when the device
            returns a short 119-byte snapshot without trailing ceiling fields.

        Raises:
            :class:`~fnirsi_dps150.DPS150ProtocolError`: If the response is
                malformed, incomplete, or contains out-of-range fields.
            :class:`~fnirsi_dps150.DPS150ConnectionError`: If the device is not
                open.
            :class:`~fnirsi_dps150.DPS150CommunicationError`: If serial
                communication fails.
        """
        payload = self._get_status_payload()

        status = _parse_device_status(payload)
        input_voltage = _read_non_negative_float32(
            payload,
            _StatusOffset.INPUT_VOLTAGE,
            "input voltage",
        )
        measurements = Measurements(
            output_voltage=_read_float32(
                payload,
                _StatusOffset.OUTPUT_VOLTAGE,
                "output voltage",
            ),
            output_current=_read_float32(
                payload,
                _StatusOffset.OUTPUT_CURRENT,
                "output current",
            ),
            output_power=_read_float32(
                payload,
                _StatusOffset.OUTPUT_POWER,
                "output power",
            ),
        )
        temperature = _read_float32(
            payload,
            _StatusOffset.TEMPERATURE,
            "temperature",
        )
        presets = tuple(
            _parse_preset_pair(payload, _StatusOffset.PRESETS_START + 8 * index)
            for index in range(_PRESET_SLOT_COUNT)
        )
        ovp_threshold = _read_non_negative_float32(
            payload,
            _StatusOffset.OVER_VOLTAGE_PROTECTION,
            "over-voltage threshold",
        )
        ocp_threshold = _read_non_negative_float32(
            payload,
            _StatusOffset.OVER_CURRENT_PROTECTION,
            "over-current threshold",
        )
        protection_settings = ProtectionSettings(
            over_power_w=_read_non_negative_float32(
                payload,
                _StatusOffset.OVER_POWER_PROTECTION,
                "over-power threshold",
            ),
            over_temperature_c=_read_non_negative_float32(
                payload,
                _StatusOffset.OVER_TEMPERATURE_PROTECTION,
                "over-temperature threshold",
            ),
            low_voltage_v=_read_non_negative_float32(
                payload,
                _StatusOffset.LOW_VOLTAGE_PROTECTION,
                "low-voltage threshold",
            ),
        )
        system_settings = _parse_system_settings(
            payload[_StatusOffset.BRIGHTNESS],
            payload[_StatusOffset.VOLUME],
            payload[_StatusOffset.METERING_ENABLED],
        )
        metering = MeteringReadings(
            capacity_ah=_read_non_negative_float32(
                payload,
                _StatusOffset.OUTPUT_CAPACITY,
                "output capacity",
            ),
            energy_wh=_read_non_negative_float32(
                payload,
                _StatusOffset.OUTPUT_ENERGY,
                "output energy",
            ),
        )
        protection_code = payload[_StatusOffset.PROTECTION_STATUS]
        protection_status = _parse_protection_status(protection_code)
        regulation_mode = _parse_regulation_mode(
            payload[_StatusOffset.REGULATION_MODE]
        )
        protection_limits = (
            _parse_protection_limits(payload)
            if len(payload) >= _FULL_STATUS_PAYLOAD_SIZE
            else None
        )
        return DeviceSnapshot(
            input_voltage=input_voltage,
            set_voltage=status.set_voltage,
            set_current=status.set_current,
            measurements=measurements,
            temperature=temperature,
            presets=presets,
            over_voltage_threshold=ovp_threshold,
            over_current_threshold=ocp_threshold,
            protection_settings=protection_settings,
            system_settings=system_settings,
            metering=metering,
            output_enabled=status.output_enabled,
            protection_code=protection_code,
            protection_status=protection_status,
            regulation_mode=regulation_mode,
            voltage_limit=status.voltage_limit,
            current_limit=status.current_limit,
            protection_limits=protection_limits,
        )

    def get_presets(self) -> tuple[Preset, ...]:
        """Read all six stored preset slots in one snapshot request.

        Returns:
            A tuple of six :class:`Preset` objects for slots 1 through 6.

        Raises:
            :class:`~fnirsi_dps150.DPS150ProtocolError`: If the response is
                malformed or contains invalid preset values.
            :class:`~fnirsi_dps150.DPS150ConnectionError`: If the device is not
                open.
            :class:`~fnirsi_dps150.DPS150CommunicationError`: If serial
                communication fails.
        """
        return self.get_snapshot().presets

    def get_measurements(self) -> Measurements:
        """Read output voltage, current, and power synchronously.

        The values come from the device's latest telemetry, which lags an
        output-enable command. On COM64 the first read after enabling reported
        near-zero voltage, and later reads settled at the setpoint. Allow the
        output to ramp before trusting these values.

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

    def get_metering(self) -> MeteringReadings:
        """Read accumulated output capacity and energy counters synchronously.

        Returns:
            A :class:`MeteringReadings` snapshot containing capacity in
            ampere-hours and energy in watt-hours.

        Raises:
            :class:`~fnirsi_dps150.DPS150ProtocolError`: If either response is
                malformed or contains a negative or non-finite value.
            :class:`~fnirsi_dps150.DPS150ConnectionError`: If the device is not
                open.
            :class:`~fnirsi_dps150.DPS150CommunicationError`: If serial
                communication fails.
        """
        return MeteringReadings(
            capacity_ah=self._get_non_negative_float_field(
                _ProtocolType.OUTPUT_CAPACITY,
                "output capacity",
            ),
            energy_wh=self._get_non_negative_float_field(
                _ProtocolType.OUTPUT_ENERGY,
                "output energy",
            ),
        )

    def get_input_voltage(self) -> float:
        """Read the device input voltage in volts.

        Returns:
            The input voltage reported by the device.

        Raises:
            :class:`~fnirsi_dps150.DPS150ProtocolError`: If the response is
                malformed or contains a negative value.
            :class:`~fnirsi_dps150.DPS150ConnectionError`: If the device is not
                open.
            :class:`~fnirsi_dps150.DPS150CommunicationError`: If serial
                communication fails.
        """
        return self._get_non_negative_float_field(
            _ProtocolType.INPUT_VOLTAGE,
            "input voltage",
        )

    def get_temperature(self) -> float:
        """Read the device temperature in degrees Celsius.

        Returns:
            The temperature reported by the device.

        Raises:
            :class:`~fnirsi_dps150.DPS150ProtocolError`: If the response is
                malformed or contains a non-finite value.
            :class:`~fnirsi_dps150.DPS150ConnectionError`: If the device is not
                open.
            :class:`~fnirsi_dps150.DPS150CommunicationError`: If serial
                communication fails.
        """
        return self._get_float_field(_ProtocolType.TEMPERATURE, "temperature")

    def get_device_info(self) -> DeviceInfo:
        """Read the model, hardware version, and firmware version.

        Returns:
            A typed snapshot of the device identity fields.

        Raises:
            :class:`~fnirsi_dps150.DPS150ProtocolError`: If a response is
                malformed or is not valid non-empty UTF-8 text.
            :class:`~fnirsi_dps150.DPS150ConnectionError`: If the device is not
                open.
            :class:`~fnirsi_dps150.DPS150CommunicationError`: If serial
                communication fails.
        """
        return DeviceInfo(
            model=self._get_text_field(_ProtocolType.MODEL, "model"),
            hardware_version=self._get_text_field(
                _ProtocolType.HARDWARE_VERSION,
                "hardware version",
            ),
            firmware_version=self._get_text_field(
                _ProtocolType.FIRMWARE_VERSION,
                "firmware version",
            ),
        )

    def get_regulation_mode(self) -> RegulationMode:
        """Read the device's constant-current or constant-voltage mode.

        Returns:
            The regulation mode reported by the device.

        Raises:
            :class:`~fnirsi_dps150.DPS150ProtocolError`: If the response is
                malformed or contains an unknown mode.
            :class:`~fnirsi_dps150.DPS150ConnectionError`: If the device is not
                open.
            :class:`~fnirsi_dps150.DPS150CommunicationError`: If serial
                communication fails.
        """
        frame = self._transport.exchange(
            _ProtocolCommand.GET,
            _ProtocolType.REGULATION_MODE,
            b"",
            expected_response=(
                _ProtocolCommand.GET,
                _ProtocolType.REGULATION_MODE,
            ),
        )
        if len(frame.payload) < 1:
            raise DPS150ProtocolError("Regulation-mode response is too short.")
        return _parse_regulation_mode(frame.payload[0])

    def get_protection_status_code(self) -> int:
        """Read the device-reported protection status without changing output.

        Returns:
            The raw status byte. On firmware V1.2, 0 was observed at idle,
            1 after OVP, 2 after OCP, 3 after OPP, 4 after OTP, and 5 after
            LVP. Other codes are not interpreted.

        Raises:
            :class:`~fnirsi_dps150.DPS150ProtocolError`: If the response does
                not contain exactly one status byte.
            :class:`~fnirsi_dps150.DPS150ConnectionError`: If the device is not
                open.
            :class:`~fnirsi_dps150.DPS150CommunicationError`: If serial
                communication fails.
        """
        frame = self._transport.exchange(
            _ProtocolCommand.GET,
            _ProtocolType.PROTECTION_STATUS,
            b"",
            expected_response=(_ProtocolCommand.GET, _ProtocolType.PROTECTION_STATUS),
        )
        if len(frame.payload) != 1:
            raise DPS150ProtocolError("Protection status must contain one byte.")
        return frame.payload[0]

    def get_protection_status(self) -> ProtectionStatus | None:
        """Read and map the device-reported protection status code.

        Returns:
            The matching :class:`ProtectionStatus` value for verified codes
            (``0`` through ``5``), or ``None`` if the device reports an
            unverified code.

        Raises:
            :class:`~fnirsi_dps150.DPS150ProtocolError`: If the response does
                not contain exactly one status byte.
            :class:`~fnirsi_dps150.DPS150ConnectionError`: If the device is not
                open.
            :class:`~fnirsi_dps150.DPS150CommunicationError`: If serial
                communication fails.
        """
        return _parse_protection_status(self.get_protection_status_code())

    def get_protection_limits(self) -> ProtectionLimits:
        """Read the device-reported upper ceilings for protection thresholds.

        Returns:
            :class:`ProtectionLimits` with the five reported ceilings.

        Raises:
            :class:`~fnirsi_dps150.DPS150ProtocolError`: If a response is
                malformed or contains a negative ceiling.
            :class:`~fnirsi_dps150.DPS150ConnectionError`: If the device is not
                open.
            :class:`~fnirsi_dps150.DPS150CommunicationError`: If serial
                communication fails.
        """
        return ProtectionLimits(
            over_voltage_v=self._get_non_negative_float_field(
                _ProtocolType.OVER_VOLTAGE_LIMIT,
                "over-voltage limit",
            ),
            over_current_a=self._get_non_negative_float_field(
                _ProtocolType.OVER_CURRENT_LIMIT,
                "over-current limit",
            ),
            over_power_w=self._get_non_negative_float_field(
                _ProtocolType.OVER_POWER_LIMIT,
                "over-power limit",
            ),
            over_temperature_c=self._get_non_negative_float_field(
                _ProtocolType.OVER_TEMPERATURE_LIMIT,
                "over-temperature limit",
            ),
            low_voltage_v=self._get_non_negative_float_field(
                _ProtocolType.LOW_VOLTAGE_LIMIT,
                "low-voltage limit",
            ),
        )

    def get_protection_settings(self) -> ProtectionSettings:
        """Read the verified OPP, OTP, and LVP thresholds.

        OPP, OTP, and LVP also have individual scalar getters; OVP and OCP are
        accessed through separate scalar methods.

        Returns:
            The three target-verified protection thresholds.

        Raises:
            :class:`~fnirsi_dps150.DPS150ProtocolError`: If a response is
                malformed or contains a negative threshold.
            :class:`~fnirsi_dps150.DPS150ConnectionError`: If the device is not
                open.
            :class:`~fnirsi_dps150.DPS150CommunicationError`: If serial
                communication fails.
        """
        return ProtectionSettings(
            over_power_w=self.get_over_power_threshold(),
            over_temperature_c=self.get_over_temperature_threshold(),
            low_voltage_v=self.get_low_voltage_threshold(),
        )

    def get_over_voltage_threshold(self) -> float:
        """Read the target-verified OVP threshold without changing it.

        The target returns this field as a float32 and it matches the OVP value
        in the status snapshot. :meth:`set_over_voltage_threshold` writes the
        same field.

        Returns:
            The device-reported over-voltage threshold in volts.

        Raises:
            :class:`~fnirsi_dps150.DPS150ProtocolError`: If the response is
                malformed or contains a negative threshold.
            :class:`~fnirsi_dps150.DPS150ConnectionError`: If the device is not
                open.
            :class:`~fnirsi_dps150.DPS150CommunicationError`: If serial
                communication fails.
        """
        return self._get_non_negative_float_field(
            _ProtocolType.OVER_VOLTAGE_PROTECTION,
            "over-voltage threshold",
        )

    def get_over_current_threshold(self) -> float:
        """Read the target-verified OCP threshold without changing it.

        The target returns this field as a float32 and it matches the OCP value
        in the status snapshot. :meth:`set_over_current_threshold` writes the
        same field.

        Returns:
            The device-reported over-current threshold in amperes.

        Raises:
            :class:`~fnirsi_dps150.DPS150ProtocolError`: If the response is
                malformed or contains a negative threshold.
            :class:`~fnirsi_dps150.DPS150ConnectionError`: If the device is not
                open.
            :class:`~fnirsi_dps150.DPS150CommunicationError`: If serial
                communication fails.
        """
        return self._get_non_negative_float_field(
            _ProtocolType.OVER_CURRENT_PROTECTION,
            "over-current threshold",
        )

    def get_over_power_threshold(self) -> float:
        """Read the target-verified OPP threshold without changing it.

        Returns:
            The device-reported over-power threshold in watts.

        Raises:
            :class:`~fnirsi_dps150.DPS150ProtocolError`: If the response is
                malformed or contains a negative threshold.
            :class:`~fnirsi_dps150.DPS150ConnectionError`: If the device is not
                open.
            :class:`~fnirsi_dps150.DPS150CommunicationError`: If serial
                communication fails.
        """
        return self._get_non_negative_float_field(
            _ProtocolType.OVER_POWER_PROTECTION,
            "over-power threshold",
        )

    def get_over_temperature_threshold(self) -> float:
        """Read the target-verified OTP threshold without changing it.

        Returns:
            The device-reported over-temperature threshold in degrees Celsius.

        Raises:
            :class:`~fnirsi_dps150.DPS150ProtocolError`: If the response is
                malformed or contains a negative threshold.
            :class:`~fnirsi_dps150.DPS150ConnectionError`: If the device is not
                open.
            :class:`~fnirsi_dps150.DPS150CommunicationError`: If serial
                communication fails.
        """
        return self._get_non_negative_float_field(
            _ProtocolType.OVER_TEMPERATURE_PROTECTION,
            "over-temperature threshold",
        )

    def get_low_voltage_threshold(self) -> float:
        """Read the target-verified LVP threshold without changing it.

        Returns:
            The device-reported low-voltage threshold in volts.

        Raises:
            :class:`~fnirsi_dps150.DPS150ProtocolError`: If the response is
                malformed or contains a negative threshold.
            :class:`~fnirsi_dps150.DPS150ConnectionError`: If the device is not
                open.
            :class:`~fnirsi_dps150.DPS150CommunicationError`: If serial
                communication fails.
        """
        return self._get_non_negative_float_field(
            _ProtocolType.LOW_VOLTAGE_PROTECTION,
            "low-voltage threshold",
        )

    def get_preset(self, slot: int) -> Preset:
        """Read stored voltage and current values without applying the preset.

        Args:
            slot: One-based preset slot from 1 through 6.

        Returns:
            :class:`~fnirsi_dps150.Preset` containing the stored values.

        Raises:
            ValueError: If ``slot`` is outside the supported range.
            :class:`~fnirsi_dps150.DPS150ProtocolError`: If either field is
                malformed or invalid.
            :class:`~fnirsi_dps150.DPS150ConnectionError`: If the device is not
                open.
            :class:`~fnirsi_dps150.DPS150CommunicationError`: If serial
                communication fails.
        """
        voltage_type, current_type = _preset_type_ids(slot)
        voltage_frame = self._transport.exchange(
            _ProtocolCommand.GET,
            voltage_type,
            b"",
            expected_response=(_ProtocolCommand.GET, voltage_type),
        )
        current_frame = self._transport.exchange(
            _ProtocolCommand.GET,
            current_type,
            b"",
            expected_response=(_ProtocolCommand.GET, current_type),
        )
        voltage = _read_float32(voltage_frame.payload, 0, "preset voltage")
        current = _read_float32(current_frame.payload, 0, "preset current")
        if voltage < 0 or current < 0:
            raise DPS150ProtocolError("Preset contains a negative value.")
        return Preset(voltage=voltage, current=current)

    def get_system_settings(self) -> SystemSettings:
        """Read verified brightness, volume, and metering settings.

        Returns:
            :class:`~fnirsi_dps150.SystemSettings` with brightness, volume, and
            metering state.

        Raises:
            :class:`~fnirsi_dps150.DPS150ProtocolError`: If any field is
                malformed or invalid.
            :class:`~fnirsi_dps150.DPS150ConnectionError`: If the device is not
                open.
            :class:`~fnirsi_dps150.DPS150CommunicationError`: If serial
                communication fails.
        """
        brightness_frame = self._transport.exchange(
            _ProtocolCommand.GET,
            _ProtocolType.BRIGHTNESS,
            b"",
            expected_response=(_ProtocolCommand.GET, _ProtocolType.BRIGHTNESS),
        )
        if len(brightness_frame.payload) < 1:
            raise DPS150ProtocolError("Brightness response is too short.")
        brightness = brightness_frame.payload[0]
        if brightness > _BRIGHTNESS_MAX:
            raise DPS150ProtocolError("Device returned an invalid brightness level.")
        volume = self.get_volume()
        metering_byte = self._get_metering_enabled_byte()

        return _parse_system_settings(
            brightness,
            volume,
            metering_byte,
        )

    def get_volume(self) -> int:
        """Read the device buzzer volume level.

        Returns:
            Volume level from 0 through 10 (where 0 is muted).

        Raises:
            :class:`~fnirsi_dps150.DPS150ProtocolError`: If the response is
                malformed or exceeds the supported range.
            :class:`~fnirsi_dps150.DPS150ConnectionError`: If the device is not
                open.
            :class:`~fnirsi_dps150.DPS150CommunicationError`: If serial
                communication fails.
        """
        frame = self._transport.exchange(
            _ProtocolCommand.GET,
            _ProtocolType.VOLUME,
            b"",
            expected_response=(_ProtocolCommand.GET, _ProtocolType.VOLUME),
        )
        if len(frame.payload) < 1:
            raise DPS150ProtocolError("Volume response is too short.")
        volume = frame.payload[0]
        if volume > _VOLUME_MAX:
            raise DPS150ProtocolError("Device returned an invalid volume level.")
        return volume

    def set_preset(self, slot: int, preset: Preset) -> None:
        """Write voltage and current values to a stored preset slot.

        This writes the native preset fields; it does not load them into the
        active setpoints. The two field writes are not atomic. A slot write on
        COM64 (firmware V1.2) survived a full power cycle after a clean
        session disconnect (``close()`` sending ``C1 00 00``), but did not
        persist when power was removed without disconnecting.

        Args:
            slot: One-based preset slot from 1 through 6.
            preset: :class:`~fnirsi_dps150.Preset` values to store.

        Raises:
            ValueError: If the slot or preset values are invalid or exceed the
                device-reported limits.
            :class:`~fnirsi_dps150.DPS150Error`: If output is enabled or serial
                status/communication fails.
        """
        voltage_type, current_type = _preset_type_ids(slot)
        if not isinstance(preset, Preset):
            raise ValueError("preset must be a Preset instance.")
        voltage, voltage_payload = _prepare_setpoint(preset.voltage, "voltage")
        current, current_payload = _prepare_setpoint(preset.current, "current")
        status = self._get_status_for_setting_write()
        if voltage > status.voltage_limit:
            raise ValueError(
                f"Preset voltage {voltage} V exceeds the device-reported limit "
                f"of {status.voltage_limit} V."
            )
        if current > status.current_limit:
            raise ValueError(
                f"Preset current {current} A exceeds the device-reported limit "
                f"of {status.current_limit} A."
            )
        self._transport.send(_ProtocolCommand.SET, voltage_type, voltage_payload)
        self._transport.send(_ProtocolCommand.SET, current_type, current_payload)

    def set_brightness(self, brightness: int) -> None:
        """Set the verified display brightness level.

        Args:
            brightness: Brightness level from 0 through 14.

        Raises:
            ValueError: If ``brightness`` is not an integer in the supported
                range.
            :class:`~fnirsi_dps150.DPS150Error`: If output is enabled, status
                cannot be read, or serial communication fails.
        """
        if (
            isinstance(brightness, bool)
            or not isinstance(brightness, int)
            or not _BRIGHTNESS_MIN <= brightness <= _BRIGHTNESS_MAX
        ):
            raise ValueError(
                f"brightness must be an integer from {_BRIGHTNESS_MIN} through "
                f"{_BRIGHTNESS_MAX}."
            )
        self._get_status_for_setting_write()
        self._transport.send(
            _ProtocolCommand.SET,
            _ProtocolType.BRIGHTNESS,
            bytes((brightness,)),
        )

    def set_volume(self, volume: int) -> None:
        """Set the buzzer volume level while output is disabled.

        Args:
            volume: Volume level from 0 through 10 (where 0 is muted).

        Raises:
            ValueError: If ``volume`` is not an integer in the supported range.
            :class:`~fnirsi_dps150.DPS150Error`: If output is enabled, status
                cannot be read, or serial communication fails.
        """
        if (
            isinstance(volume, bool)
            or not isinstance(volume, int)
            or not _VOLUME_MIN <= volume <= _VOLUME_MAX
        ):
            raise ValueError(
                f"volume must be an integer from {_VOLUME_MIN} through "
                f"{_VOLUME_MAX}."
            )
        self._get_status_for_setting_write()
        self._transport.send(
            _ProtocolCommand.SET,
            _ProtocolType.VOLUME,
            bytes((volume,)),
        )

    def set_metering_enabled(self, enabled: bool) -> None:
        """Enable or pause capacity and energy metering.

        Confirmed on COM64 (firmware V1.2) with output enabled or disabled:
        ``True`` enables ``Ah``/``Wh`` accumulation, ``False`` pauses
        accumulation while retaining the current counters, and a ``False`` to
        ``True`` transition clears the hardware counters to zero.

        Args:
            enabled: ``True`` to enable metering, ``False`` to pause it.

        Raises:
            ValueError: If ``enabled`` is not a bool.
            :class:`~fnirsi_dps150.DPS150ConnectionError`: If the device is not
                open.
            :class:`~fnirsi_dps150.DPS150CommunicationError`: If serial
                communication fails.
        """
        if not isinstance(enabled, bool):
            raise ValueError("enabled must be a bool.")
        self._transport.send(
            _ProtocolCommand.SET,
            _ProtocolType.METERING_ENABLED,
            bytes((int(enabled),)),
        )

    def reset_metering(self) -> None:
        """Reset accumulated capacity and energy counters while keeping state.

        Reads the current metering enable state and pulses ``METERING_ENABLED``
        across a ``0 -> 1`` transition, returning it to its prior state. The
        two writes are sent separately and are not atomic.

        Raises:
            :class:`~fnirsi_dps150.DPS150ProtocolError`: If the reported
                metering enable byte is malformed or invalid.
            :class:`~fnirsi_dps150.DPS150ConnectionError`: If the device is not
                open.
            :class:`~fnirsi_dps150.DPS150CommunicationError`: If serial
                communication fails.
        """
        was_enabled = bool(self._get_metering_enabled_byte())
        if was_enabled:
            sequence = (0, 1)
        else:
            sequence = (1, 0)
        for state in sequence:
            self._transport.send(
                _ProtocolCommand.SET,
                _ProtocolType.METERING_ENABLED,
                bytes((state,)),
            )

    def _get_metering_enabled_byte(self) -> int:
        """Read and validate the raw metering-enable byte (0 or 1)."""
        frame = self._transport.exchange(
            _ProtocolCommand.GET,
            _ProtocolType.METERING_ENABLED,
            b"",
            expected_response=(
                _ProtocolCommand.GET,
                _ProtocolType.METERING_ENABLED,
            ),
        )
        if len(frame.payload) < 1:
            raise DPS150ProtocolError("Metering response is too short.")
        raw_value = frame.payload[0]
        if raw_value not in (0, 1):
            raise DPS150ProtocolError("Device returned an invalid metering state.")
        return raw_value

    def set_over_voltage_threshold(self, voltage: float) -> None:
        """Write the OVP threshold while output is disabled.

        Args:
            voltage: Positive threshold in volts.

        Raises:
            ValueError: If the threshold is invalid or exceeds the reported
                device OVP ceiling.
            :class:`~fnirsi_dps150.DPS150Error`: If output is enabled or serial
                status/communication fails.
        """
        self._set_threshold(
            _ProtocolType.OVER_VOLTAGE_PROTECTION,
            voltage,
            "over-voltage threshold",
            "V",
            require_positive=True,
        )

    def set_over_current_threshold(self, current: float) -> None:
        """Write the OCP threshold while output is disabled.

        Args:
            current: Positive threshold in amperes.

        Raises:
            ValueError: If the threshold is invalid or exceeds the reported
                device OCP ceiling.
            :class:`~fnirsi_dps150.DPS150Error`: If output is enabled or serial
                status/communication fails.
        """
        self._set_threshold(
            _ProtocolType.OVER_CURRENT_PROTECTION,
            current,
            "over-current threshold",
            "A",
            require_positive=True,
        )

    def set_over_power_threshold(self, watts: float) -> None:
        """Write the OPP threshold while output is disabled.

        Args:
            watts: Non-negative threshold in watts.

        Raises:
            ValueError: If the threshold is invalid or exceeds the reported
                device OPP ceiling.
            :class:`~fnirsi_dps150.DPS150Error`: If output is enabled or serial
                status/communication fails.
        """
        self._set_threshold(
            _ProtocolType.OVER_POWER_PROTECTION,
            watts,
            "over-power threshold",
            "W",
            require_positive=False,
        )

    def set_over_temperature_threshold(self, celsius: float) -> None:
        """Write the OTP threshold while output is disabled.

        Args:
            celsius: Non-negative threshold in degrees Celsius.

        Raises:
            ValueError: If the threshold is invalid or exceeds the reported
                device OTP ceiling.
            :class:`~fnirsi_dps150.DPS150Error`: If output is enabled or serial
                status/communication fails.
        """
        self._set_threshold(
            _ProtocolType.OVER_TEMPERATURE_PROTECTION,
            celsius,
            "over-temperature threshold",
            "°C",
            require_positive=False,
        )

    def set_low_voltage_threshold(self, volts: float) -> None:
        """Write the LVP threshold while output is disabled.

        Args:
            volts: Non-negative threshold in volts.

        Raises:
            ValueError: If the threshold is invalid or exceeds the reported
                device LVP ceiling.
            :class:`~fnirsi_dps150.DPS150Error`: If output is enabled or serial
                status/communication fails.
        """
        self._set_threshold(
            _ProtocolType.LOW_VOLTAGE_PROTECTION,
            volts,
            "low-voltage threshold",
            "V",
            require_positive=False,
        )

    def _set_threshold(
        self,
        type_id: _ProtocolType,
        threshold: float,
        field_name: str,
        unit: str,
        *,
        require_positive: bool,
    ) -> None:
        """Validate, check reported ceiling, and write one protection threshold."""
        value, payload = _prepare_setpoint(threshold, field_name)
        if require_positive and value == 0:
            raise ValueError(f"{field_name} must be positive.")
        _, limits = self._get_status_and_limits_for_setting_write()
        if limits is not None:
            ceiling = _protection_limit_for(limits, type_id)
            if value > ceiling:
                raise ValueError(
                    f"{field_name} {value} {unit} exceeds the device-reported "
                    f"limit of {ceiling} {unit}."
                )
        self._transport.send(_ProtocolCommand.SET, type_id, payload)

    def set_protection_settings(self, settings: ProtectionSettings) -> None:
        """Write OPP, OTP, and LVP thresholds while output is disabled.

        The three writes are sent separately and are not atomic. OPP, OTP, and
        LVP also have individual scalar setters; OVP and OCP are written
        through separate scalar methods.

        Args:
            settings: Verified thresholds to write.

        Raises:
            ValueError: If ``settings`` or any threshold is invalid or exceeds
                the reported device ceiling.
            :class:`~fnirsi_dps150.DPS150Error`: If output is enabled or serial
                status/communication fails.
        """
        if not isinstance(settings, ProtectionSettings):
            raise ValueError("settings must be a ProtectionSettings instance.")
        values = (
            (
                _ProtocolType.OVER_POWER_PROTECTION,
                settings.over_power_w,
                "over-power threshold",
                "W",
            ),
            (
                _ProtocolType.OVER_TEMPERATURE_PROTECTION,
                settings.over_temperature_c,
                "over-temperature threshold",
                "°C",
            ),
            (
                _ProtocolType.LOW_VOLTAGE_PROTECTION,
                settings.low_voltage_v,
                "low-voltage threshold",
                "V",
            ),
        )
        prepared = tuple(
            (type_id, *_prepare_setpoint(value, name), name, unit)
            for type_id, value, name, unit in values
        )
        _, limits = self._get_status_and_limits_for_setting_write()
        if limits is not None:
            for type_id, value, _, name, unit in prepared:
                ceiling = _protection_limit_for(limits, type_id)
                if value > ceiling:
                    raise ValueError(
                        f"{name} {value} {unit} exceeds the device-reported "
                        f"limit of {ceiling} {unit}."
                    )
        for type_id, _, payload, _, _ in prepared:
            self._transport.send(_ProtocolCommand.SET, type_id, payload)

    def set_setpoints(self, voltage: float, current: float) -> None:
        """Set both output voltage and current limit without enabling output.

        Both inputs are validated against the device-reported limits from a
        single status read before either register write is sent. The two
        writes are sent separately and are not atomic.

        Args:
            voltage: Non-negative setpoint in volts.
            current: Non-negative current limit in amperes.

        Raises:
            ValueError: If either value is invalid or exceeds the reported
                device limit.
            :class:`~fnirsi_dps150.DPS150Error`: If status read or serial
                communication fails.
        """
        voltage_value, voltage_payload = _prepare_setpoint(voltage, "voltage")
        current_value, current_payload = _prepare_setpoint(current, "current")
        status = self.get_status()
        if voltage_value > status.voltage_limit:
            raise ValueError(
                f"Voltage {voltage_value} V exceeds the device-reported limit "
                f"of {status.voltage_limit} V."
            )
        if current_value > status.current_limit:
            raise ValueError(
                f"Current {current_value} A exceeds the device-reported limit "
                f"of {status.current_limit} A."
            )
        self._transport.send(
            _ProtocolCommand.SET,
            _ProtocolType.VOLTAGE_SETPOINT,
            voltage_payload,
        )
        self._transport.send(
            _ProtocolCommand.SET,
            _ProtocolType.CURRENT_SETPOINT,
            current_payload,
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

        The method does not read back the resulting state. Command/state
        readback was verified on COM64 without a load, and a separately gated
        loaded check reached the 10 V setpoint into a nominal 180 Ω load at
        about 0.48 W. Higher-power loaded behavior and emergency-shutdown
        reliability were not verified.

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

    def _get_status_payload(self) -> bytes:
        """Read and length-validate the raw ``GET 0xFF`` status payload."""
        frame = self._transport.exchange(
            _ProtocolCommand.GET,
            _ProtocolType.STATUS,
            b"",
            expected_response=(_ProtocolCommand.GET, _ProtocolType.STATUS),
        )
        if len(frame.payload) < _STATUS_PAYLOAD_SIZE:
            raise DPS150ProtocolError("Status response is too short.")
        return frame.payload

    def _get_status_for_setting_write(self) -> DeviceStatus:
        """Read status after requiring settings writes to be output-OFF."""
        return self._get_status_and_limits_for_setting_write()[0]

    def _get_status_and_limits_for_setting_write(
        self,
    ) -> tuple[DeviceStatus, ProtectionLimits | None]:
        """Read status and optional protection ceilings, requiring output OFF.

        Returns:
            Current :class:`DeviceStatus` and :class:`ProtectionLimits` if
            the device returned a 139-byte snapshot, otherwise ``None``.

        Raises:
            :class:`~fnirsi_dps150.DPS150Error`: If output is enabled or status
                reading fails.
        """
        payload = self._get_status_payload()
        status = _parse_device_status(payload)
        if status.output_enabled:
            raise DPS150Error(
                "Preset, system-setting, and protection writes require output disabled."
            )
        limits = (
            _parse_protection_limits(payload)
            if len(payload) >= _FULL_STATUS_PAYLOAD_SIZE
            else None
        )
        return status, limits

    def _get_float_field(self, type_id: _ProtocolType, field_name: str) -> float:
        """Read one float32-valued field by its target-verified type."""
        frame = self._transport.exchange(
            _ProtocolCommand.GET,
            type_id,
            b"",
            expected_response=(_ProtocolCommand.GET, type_id),
        )
        return _read_float32(frame.payload, 0, field_name)

    def _get_non_negative_float_field(
        self,
        type_id: _ProtocolType,
        field_name: str,
    ) -> float:
        """Read one finite, non-negative float32 field by its type."""
        value = self._get_float_field(type_id, field_name)
        if value < 0:
            raise DPS150ProtocolError(f"Device returned a negative {field_name}.")
        return value

    def _get_text_field(self, type_id: _ProtocolType, field_name: str) -> str:
        """Read and validate one UTF-8 text field."""
        frame = self._transport.exchange(
            _ProtocolCommand.GET,
            type_id,
            b"",
            expected_response=(_ProtocolCommand.GET, type_id),
        )
        try:
            value = frame.payload.decode("utf-8").rstrip("\x00").strip()
        except UnicodeDecodeError as error:
            raise DPS150ProtocolError(
                f"Device returned invalid UTF-8 for {field_name}."
            ) from error
        if not value:
            raise DPS150ProtocolError(f"Device returned an empty {field_name}.")
        return value

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
        """Disconnect and close the host serial port when leaving ``with``."""
        if exception_type is None:
            self.close()
            return
        if not self._transport.is_open:
            return
        try:
            with contextlib.suppress(DPS150Error):
                self._transport.send(
                    _ProtocolCommand.CONNECT,
                    _ProtocolType.SESSION,
                    b"\x00",
                )
                self._transport.wait_for_command_gap()
        finally:
            with contextlib.suppress(DPS150Error):
                self._transport.close()


def _parse_device_status(payload: bytes) -> DeviceStatus:
    """Decode setpoints, output state, and limits from a status payload."""
    output_enabled = payload[_StatusOffset.OUTPUT_ENABLED]
    if output_enabled not in (0, 1):
        raise DPS150ProtocolError("Status contains an invalid output state.")
    voltage_limit = _read_non_negative_float32(
        payload,
        _StatusOffset.VOLTAGE_LIMIT,
        "voltage limit",
    )
    current_limit = _read_non_negative_float32(
        payload,
        _StatusOffset.CURRENT_LIMIT,
        "current limit",
    )
    return DeviceStatus(
        set_voltage=_read_float32(
            payload,
            _StatusOffset.VOLTAGE_SETPOINT,
            "voltage setpoint",
        ),
        set_current=_read_float32(
            payload,
            _StatusOffset.CURRENT_SETPOINT,
            "current setpoint",
        ),
        output_enabled=bool(output_enabled),
        voltage_limit=voltage_limit,
        current_limit=current_limit,
    )


def _parse_preset_pair(payload: bytes, offset: int) -> Preset:
    """Decode one preset voltage/current pair at ``offset``."""
    voltage = _read_non_negative_float32(payload, offset, "preset voltage")
    current = _read_non_negative_float32(payload, offset + 4, "preset current")
    return Preset(voltage=voltage, current=current)


def _parse_system_settings(
    brightness: int,
    volume: int,
    metering_enabled: int,
) -> SystemSettings:
    """Validate and construct :class:`SystemSettings` from raw bytes."""
    if brightness > _BRIGHTNESS_MAX:
        raise DPS150ProtocolError("Device returned an invalid brightness level.")
    if volume > _VOLUME_MAX:
        raise DPS150ProtocolError("Device returned an invalid volume level.")
    if metering_enabled not in (0, 1):
        raise DPS150ProtocolError("Device returned an invalid metering state.")
    return SystemSettings(
        brightness=brightness,
        metering_enabled=bool(metering_enabled),
        volume=volume,
    )


def _parse_regulation_mode(raw_mode: int) -> RegulationMode:
    """Validate and convert a raw regulation-mode byte."""
    try:
        return RegulationMode(raw_mode)
    except ValueError as error:
        raise DPS150ProtocolError(
            "Device returned an invalid regulation mode."
        ) from error


def _parse_protection_status(code: int) -> ProtectionStatus | None:
    """Map a target-verified protection byte, returning ``None`` if unknown."""
    try:
        return ProtectionStatus(code)
    except ValueError:
        return None


def _parse_protection_limits(payload: bytes) -> ProtectionLimits:
    """Decode protection ceiling fields from a 139-byte snapshot payload."""
    return ProtectionLimits(
        over_voltage_v=_read_non_negative_float32(
            payload,
            _StatusOffset.OVER_VOLTAGE_LIMIT,
            "over-voltage limit",
        ),
        over_current_a=_read_non_negative_float32(
            payload,
            _StatusOffset.OVER_CURRENT_LIMIT,
            "over-current limit",
        ),
        over_power_w=_read_non_negative_float32(
            payload,
            _StatusOffset.OVER_POWER_LIMIT,
            "over-power limit",
        ),
        over_temperature_c=_read_non_negative_float32(
            payload,
            _StatusOffset.OVER_TEMPERATURE_LIMIT,
            "over-temperature limit",
        ),
        low_voltage_v=_read_non_negative_float32(
            payload,
            _StatusOffset.LOW_VOLTAGE_LIMIT,
            "low-voltage limit",
        ),
    )


def _protection_limit_for(
    limits: ProtectionLimits,
    type_id: _ProtocolType,
) -> float:
    """Return the device-reported ceiling corresponding to ``type_id``."""
    ceiling_by_type = {
        _ProtocolType.OVER_VOLTAGE_PROTECTION: limits.over_voltage_v,
        _ProtocolType.OVER_CURRENT_PROTECTION: limits.over_current_a,
        _ProtocolType.OVER_POWER_PROTECTION: limits.over_power_w,
        _ProtocolType.OVER_TEMPERATURE_PROTECTION: limits.over_temperature_c,
        _ProtocolType.LOW_VOLTAGE_PROTECTION: limits.low_voltage_v,
    }
    return ceiling_by_type[type_id]


def _read_non_negative_float32(
    payload: bytes,
    offset: int,
    field_name: str,
) -> float:
    """Read one finite, non-negative float32 field from ``payload``."""
    value = _read_float32(payload, offset, field_name)
    if value < 0:
        raise DPS150ProtocolError(f"Device returned a negative {field_name}.")
    return value


def _preset_type_ids(slot: int) -> tuple[_ProtocolType, _ProtocolType]:
    """Map a one-based preset slot to its native voltage and current types.

    Args:
        slot: Preset slot from 1 through 6.

    Returns:
        Voltage and current protocol types for the slot.

    Raises:
        ValueError: If ``slot`` is not an integer from 1 through 6.
    """
    if (
        isinstance(slot, bool)
        or not isinstance(slot, int)
        or not _PRESET_SLOT_MIN <= slot <= _PRESET_SLOT_COUNT
    ):
        raise ValueError(
            f"slot must be an integer from {_PRESET_SLOT_MIN} through "
            f"{_PRESET_SLOT_COUNT}."
        )
    voltage_type = int(_ProtocolType.PRESET_1_VOLTAGE) + 2 * (slot - 1)
    return _ProtocolType(voltage_type), _ProtocolType(voltage_type + 1)


def _read_float32(payload: bytes, offset: int, field_name: str) -> float:
    """Unpack and validate one finite little-endian float32 field."""
    if len(payload) < offset + 4:
        raise DPS150ProtocolError(f"Response is missing {field_name}.")
    value = struct.unpack_from("<f", payload, offset)[0]
    if not math.isfinite(value):
        raise DPS150ProtocolError(f"Device returned a non-finite {field_name}.")
    return value


def _prepare_setpoint(value: float, field_name: str) -> tuple[float, bytes]:
    """Validate and pack one finite non-negative float32 value."""
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
