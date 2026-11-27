"""Hardware-free tests for the public device connection and status API."""

import pathlib
import re
import struct
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import serial

import fnirsi_dps150
from fnirsi_dps150 import (
    DPS150,
    DeviceInfo,
    DeviceSnapshot,
    Measurements,
    MeteringReadings,
    Preset,
    ProtectionLimits,
    ProtectionSettings,
    ProtectionStatus,
    SystemSettings,
    find_ports,
)
from fnirsi_dps150._protocol import _encode_frame
from fnirsi_dps150._transport import _SerialTransport
from fnirsi_dps150.definitions.exceptions import (
    DPS150CommunicationError,
    DPS150ConnectionError,
    DPS150Error,
    DPS150ProtocolError,
    DPS150TimeoutError,
)
from fnirsi_dps150.definitions.namespace import (
    RegulationMode,
    _ProtocolCommand,
    _ProtocolType,
)

_DISCONNECT_FRAME = _encode_frame(_ProtocolCommand.CONNECT, _ProtocolType.SESSION, b"\x00")


class FakeSerial:
    def __init__(
        self,
        response: bytes = b"",
        max_read_size: int = 1024,
        write_error: OSError | None = None,
        write_error_at: int | None = None,
        read_error: Exception | None = None,
        stale_prefix: bytes = b"",
        reset_input_error: Exception | None = None,
        close_error: Exception | None = None,
    ) -> None:
        self.timeout: float | None = 1.0
        self.is_open = True
        self.stale_prefix = bytearray(stale_prefix)
        self.response = bytearray(response)
        self.max_read_size = max_read_size
        self.writes: list[bytes] = []
        self.close_calls = 0
        self.reset_input_buffer_calls = 0
        self.write_error = write_error
        self.write_error_at = write_error_at
        self.write_call_count = 0
        self.read_error = read_error
        self.reset_input_error = reset_input_error
        self.close_error = close_error

    def reset_input_buffer(self) -> None:
        self.reset_input_buffer_calls += 1
        if self.reset_input_error is not None:
            raise self.reset_input_error
        self.stale_prefix.clear()

    def write(self, packet: bytes) -> int:
        self.write_call_count += 1
        if self.write_error is not None and (
            self.write_error_at is None
            or self.write_call_count == self.write_error_at
        ):
            raise self.write_error
        self.writes.append(packet)
        return len(packet)

    def read(self, count: int) -> bytes:
        if self.read_error is not None:
            raise self.read_error
        if self.stale_prefix:
            read_size = min(count, self.max_read_size, len(self.stale_prefix))
            result = bytes(self.stale_prefix[:read_size])
            del self.stale_prefix[:read_size]
            return result
        if not self.response:
            return b""
        read_size = min(count, self.max_read_size, len(self.response))
        result = bytes(self.response[:read_size])
        del self.response[:read_size]
        return result

    def close(self) -> None:
        self.close_calls += 1
        self.is_open = False
        if self.close_error is not None:
            raise self.close_error


def make_status_response(
    output_enabled: int = 0,
    set_voltage: float = 12.0,
    set_current: float = 5.0,
    voltage_limit: float = 20.0,
    current_limit: float = 5.1,
) -> bytes:
    payload = bytearray(119)
    struct.pack_into("<f", payload, 4, set_voltage)
    struct.pack_into("<f", payload, 8, set_current)
    payload[107] = output_enabled
    struct.pack_into("<f", payload, 111, voltage_limit)
    struct.pack_into("<f", payload, 115, current_limit)
    return _encode_frame(0xA1, 0xFF, bytes(payload), header=0xF0)


def make_full_status_response(
    *,
    input_voltage: float = 12.05,
    set_voltage: float = 10.0,
    set_current: float = 5.0,
    output_voltage: float = 0.0,
    output_current: float = 0.0,
    output_power: float = 0.0,
    temperature: float = 26.8,
    presets: tuple[tuple[float, float], ...] = ((5.0, 1.0),) * 6,
    ovp: float = 30.0,
    ocp: float = 5.1,
    opp: float = 150.0,
    otp: float = 80.0,
    lvp: float = 5.0,
    brightness: int = 10,
    volume: int = 0,
    metering_enabled: int = 0,
    capacity_ah: float = 0.0,
    energy_wh: float = 0.0,
    output_enabled: int = 0,
    protection_code: int = 0,
    regulation_mode: int = 1,
    voltage_limit: float = 11.85,
    current_limit: float = 5.1,
    ovp_limit: float = 30.0,
    ocp_limit: float = 5.1,
    opp_limit: float = 150.0,
    otp_limit: float = 99.0,
    lvp_limit: float = 30.0,
) -> bytes:
    payload = bytearray(139)
    struct.pack_into("<f", payload, 0, input_voltage)
    struct.pack_into("<f", payload, 4, set_voltage)
    struct.pack_into("<f", payload, 8, set_current)
    struct.pack_into("<f", payload, 12, output_voltage)
    struct.pack_into("<f", payload, 16, output_current)
    struct.pack_into("<f", payload, 20, output_power)
    struct.pack_into("<f", payload, 24, temperature)
    for index, (preset_v, preset_i) in enumerate(presets):
        struct.pack_into("<f", payload, 28 + 8 * index, preset_v)
        struct.pack_into("<f", payload, 32 + 8 * index, preset_i)
    struct.pack_into("<f", payload, 76, ovp)
    struct.pack_into("<f", payload, 80, ocp)
    struct.pack_into("<f", payload, 84, opp)
    struct.pack_into("<f", payload, 88, otp)
    struct.pack_into("<f", payload, 92, lvp)
    payload[96] = brightness
    payload[97] = volume
    payload[98] = metering_enabled
    struct.pack_into("<f", payload, 99, capacity_ah)
    struct.pack_into("<f", payload, 103, energy_wh)
    payload[107] = output_enabled
    payload[108] = protection_code
    payload[109] = regulation_mode
    struct.pack_into("<f", payload, 111, voltage_limit)
    struct.pack_into("<f", payload, 115, current_limit)
    struct.pack_into("<f", payload, 119, ovp_limit)
    struct.pack_into("<f", payload, 123, ocp_limit)
    struct.pack_into("<f", payload, 127, opp_limit)
    struct.pack_into("<f", payload, 131, otp_limit)
    struct.pack_into("<f", payload, 135, lvp_limit)
    return _encode_frame(0xA1, 0xFF, bytes(payload), header=0xF0)


def make_measurements_response(
    voltage: float = 12.0,
    current: float = 0.5,
    power: float = 6.0,
) -> bytes:
    payload = struct.pack("<3f", voltage, current, power)
    return _encode_frame(0xA1, 195, payload, header=0xF0)


def make_field_response(type_id: int, payload: bytes) -> bytes:
    return _encode_frame(
        _ProtocolCommand.GET,
        type_id,
        payload,
        header=0xF0,
    )


class DeviceTests(unittest.TestCase):
    def setUp(self) -> None:
        sleep_patcher = patch("fnirsi_dps150._transport.time.sleep")
        sleep_patcher.start()
        self.addCleanup(sleep_patcher.stop)

    def test_construction_does_not_open_serial_port(self) -> None:
        with patch("fnirsi_dps150._transport.serial.Serial") as serial_factory:
            device = DPS150(port="COM64")

        serial_factory.assert_not_called()
        self.assertIsInstance(device, DPS150)

    def test_package_version_matches_pyproject(self) -> None:
        pyproject_path = pathlib.Path(__file__).resolve().parents[1] / "pyproject.toml"
        pyproject_text = pyproject_path.read_text(encoding="utf-8")
        match = re.search(r'^version\s*=\s*"([^"]+)"', pyproject_text, re.MULTILINE)
        self.assertIsNotNone(match)
        assert match is not None
        self.assertEqual(fnirsi_dps150.__version__, "0.1.0")
        self.assertEqual(fnirsi_dps150.__version__, match.group(1))

    def test_open_sends_session_handshake_and_close_sends_disconnect(self) -> None:
        fake_serial = FakeSerial()
        with patch(
            "fnirsi_dps150._transport.serial.Serial",
            return_value=fake_serial,
        ) as serial_factory:
            device = DPS150(port="COM64")
            device.open()
            device.close()
            device.close()

        self.assertEqual(
            fake_serial.writes,
            [_encode_frame(0xC1, 0x00, b"\x01"), _DISCONNECT_FRAME],
        )
        self.assertEqual(fake_serial.close_calls, 1)
        self.assertEqual(serial_factory.call_args.kwargs["baudrate"], 115200)
        self.assertEqual(serial_factory.call_args.kwargs["timeout"], 1.0)
        self.assertFalse(serial_factory.call_args.kwargs["rtscts"])

    def test_close_keep_locked_skips_disconnect_and_validates_flag(self) -> None:
        fake_serial = FakeSerial()
        with patch(
            "fnirsi_dps150._transport.serial.Serial",
            return_value=fake_serial,
        ):
            device = DPS150(port="COM64")
            device.open()
            with self.assertRaises(ValueError):
                device.close(keep_locked=1)  # type: ignore[arg-type]
            device.close(keep_locked=True)

        self.assertEqual(fake_serial.writes, [_encode_frame(0xC1, 0x00, b"\x01")])
        self.assertEqual(fake_serial.close_calls, 1)

    def test_close_still_closes_port_when_disconnect_write_fails(self) -> None:
        write_error = OSError("disconnect failed")
        fake_serial = FakeSerial(write_error=write_error, write_error_at=2)
        with patch(
            "fnirsi_dps150._transport.serial.Serial",
            return_value=fake_serial,
        ):
            device = DPS150(port="COM64")
            device.open()
            with self.assertRaises(DPS150CommunicationError) as raised:
                device.close()

        self.assertIs(raised.exception.__cause__, write_error)
        self.assertEqual(fake_serial.close_calls, 1)

    def test_get_status_handles_fragmented_response(self) -> None:
        fake_serial = FakeSerial(make_status_response(), max_read_size=2)
        with patch(
            "fnirsi_dps150._transport.serial.Serial",
            return_value=fake_serial,
        ):
            with DPS150(port="COM64") as device:
                status = device.get_status()

        self.assertEqual(status.set_voltage, 12.0)
        self.assertEqual(status.set_current, 5.0)
        self.assertFalse(status.output_enabled)
        self.assertEqual(status.voltage_limit, 20.0)
        self.assertAlmostEqual(status.current_limit, 5.1, places=6)
        self.assertEqual(
            fake_serial.writes,
            [
                _encode_frame(0xC1, 0x00, b"\x01"),
                _encode_frame(0xA1, 0xFF),
                _DISCONNECT_FRAME,
            ],
        )
        self.assertEqual(fake_serial.close_calls, 1)

    def test_get_status_skips_unmatched_telemetry_frames(self) -> None:
        telemetry = _encode_frame(0xA1, 195, bytes(12), header=0xF0)
        fake_serial = FakeSerial(telemetry + make_status_response(), max_read_size=3)
        with patch(
            "fnirsi_dps150._transport.serial.Serial",
            return_value=fake_serial,
        ):
            with DPS150(port="COM64") as device:
                status = device.get_status()

        self.assertFalse(status.output_enabled)
        self.assertEqual(status.set_voltage, 12.0)
        self.assertEqual(
            fake_serial.writes,
            [
                _encode_frame(0xC1, 0x00, b"\x01"),
                _encode_frame(0xA1, 0xFF),
                _DISCONNECT_FRAME,
            ],
        )

    def test_get_status_rejects_invalid_output_state(self) -> None:
        fake_serial = FakeSerial(make_status_response(output_enabled=2))
        with patch(
            "fnirsi_dps150._transport.serial.Serial",
            return_value=fake_serial,
        ):
            device = DPS150(port="COM64")
            device.open()
            with self.assertRaises(DPS150ProtocolError):
                device.get_status()
            device.close()

    def test_get_status_rejects_short_snapshot(self) -> None:
        response = _encode_frame(0xA1, 0xFF, bytes(108), header=0xF0)
        fake_serial = FakeSerial(response)
        with patch(
            "fnirsi_dps150._transport.serial.Serial",
            return_value=fake_serial,
        ):
            with DPS150(port="COM64") as device:
                with self.assertRaises(DPS150ProtocolError):
                    device.get_status()

    def test_get_measurements_returns_typed_values(self) -> None:
        fake_serial = FakeSerial(make_measurements_response())
        with patch(
            "fnirsi_dps150._transport.serial.Serial",
            return_value=fake_serial,
        ):
            with DPS150(port="COM64") as device:
                measurements = device.get_measurements()

        self.assertEqual(
            measurements,
            Measurements(output_voltage=12.0, output_current=0.5, output_power=6.0),
        )
        self.assertEqual(
            fake_serial.writes,
            [
                _encode_frame(0xC1, 0x00, b"\x01"),
                _encode_frame(0xA1, 195),
                _DISCONNECT_FRAME,
            ],
        )

    def test_get_measurements_rejects_non_finite_values(self) -> None:
        fake_serial = FakeSerial(make_measurements_response(voltage=float("nan")))
        with patch(
            "fnirsi_dps150._transport.serial.Serial",
            return_value=fake_serial,
        ):
            with DPS150(port="COM64") as device:
                with self.assertRaises(DPS150ProtocolError):
                    device.get_measurements()

    def test_get_input_voltage_and_temperature_reads_typed_fields(self) -> None:
        fake_serial = FakeSerial(
            make_field_response(
                _ProtocolType.INPUT_VOLTAGE,
                struct.pack("<f", 19.99),
            )
            + make_field_response(
                _ProtocolType.TEMPERATURE,
                struct.pack("<f", 29.25),
            )
        )
        with patch(
            "fnirsi_dps150._transport.serial.Serial",
            return_value=fake_serial,
        ):
            with DPS150(port="COM64") as device:
                input_voltage = device.get_input_voltage()
                temperature = device.get_temperature()

        self.assertAlmostEqual(input_voltage, 19.99, places=2)
        self.assertEqual(temperature, 29.25)
        self.assertEqual(
            fake_serial.writes,
            [
                _encode_frame(_ProtocolCommand.CONNECT, _ProtocolType.SESSION, b"\x01"),
                _encode_frame(_ProtocolCommand.GET, _ProtocolType.INPUT_VOLTAGE),
                _encode_frame(_ProtocolCommand.GET, _ProtocolType.TEMPERATURE),
                _DISCONNECT_FRAME,
            ],
        )

    def test_get_device_info_decodes_target_text_fields(self) -> None:
        fake_serial = FakeSerial(
            make_field_response(_ProtocolType.MODEL, b"DPS-150")
            + make_field_response(_ProtocolType.HARDWARE_VERSION, b"V1.0")
            + make_field_response(_ProtocolType.FIRMWARE_VERSION, b"V1.2")
        )
        with patch(
            "fnirsi_dps150._transport.serial.Serial",
            return_value=fake_serial,
        ):
            with DPS150(port="COM64") as device:
                info = device.get_device_info()

        self.assertEqual(
            info,
            DeviceInfo(
                model="DPS-150",
                hardware_version="V1.0",
                firmware_version="V1.2",
            ),
        )
        self.assertEqual(
            fake_serial.writes,
            [
                _encode_frame(_ProtocolCommand.CONNECT, _ProtocolType.SESSION, b"\x01"),
                _encode_frame(_ProtocolCommand.GET, _ProtocolType.MODEL),
                _encode_frame(_ProtocolCommand.GET, _ProtocolType.HARDWARE_VERSION),
                _encode_frame(_ProtocolCommand.GET, _ProtocolType.FIRMWARE_VERSION),
                _DISCONNECT_FRAME,
            ],
        )

    def test_get_device_info_rejects_invalid_utf8(self) -> None:
        fake_serial = FakeSerial(
            make_field_response(_ProtocolType.MODEL, b"\xff")
        )
        with patch(
            "fnirsi_dps150._transport.serial.Serial",
            return_value=fake_serial,
        ):
            with DPS150(port="COM64") as device:
                with self.assertRaises(DPS150ProtocolError):
                    device.get_device_info()

    def test_get_regulation_mode_reads_known_modes(self) -> None:
        fake_serial = FakeSerial(
            make_field_response(_ProtocolType.REGULATION_MODE, b"\x01")
            + make_field_response(_ProtocolType.REGULATION_MODE, b"\x00")
        )
        with patch(
            "fnirsi_dps150._transport.serial.Serial",
            return_value=fake_serial,
        ):
            with DPS150(port="COM64") as device:
                constant_voltage = device.get_regulation_mode()
                constant_current = device.get_regulation_mode()

        self.assertEqual(constant_voltage, RegulationMode.CV)
        self.assertEqual(constant_current, RegulationMode.CC)
        self.assertEqual(
            fake_serial.writes,
            [
                _encode_frame(_ProtocolCommand.CONNECT, _ProtocolType.SESSION, b"\x01"),
                _encode_frame(_ProtocolCommand.GET, _ProtocolType.REGULATION_MODE),
                _encode_frame(_ProtocolCommand.GET, _ProtocolType.REGULATION_MODE),
                _DISCONNECT_FRAME,
            ],
        )

    def test_get_regulation_mode_rejects_unknown_value(self) -> None:
        fake_serial = FakeSerial(
            make_field_response(_ProtocolType.REGULATION_MODE, b"\x02")
        )
        with patch(
            "fnirsi_dps150._transport.serial.Serial",
            return_value=fake_serial,
        ):
            with DPS150(port="COM64") as device:
                with self.assertRaises(DPS150ProtocolError):
                    device.get_regulation_mode()

    def test_get_protection_status_code_reads_byte_without_mapping_it(self) -> None:
        for payload in (b"\x00", b"\xff", b"", b"\x00\x01"):
            with self.subTest(payload=payload):
                fake_serial = FakeSerial(make_field_response(220, payload))
                with patch(
                    "fnirsi_dps150._transport.serial.Serial",
                    return_value=fake_serial,
                ):
                    with DPS150(port="COM64") as device:
                        if len(payload) == 1:
                            self.assertEqual(
                                device.get_protection_status_code(), payload[0]
                            )
                        else:
                            with self.assertRaises(DPS150ProtocolError):
                                device.get_protection_status_code()
                self.assertEqual(
                    fake_serial.writes[1:],
                    [_encode_frame(_ProtocolCommand.GET, 220), _DISCONNECT_FRAME],
                )

    def test_get_protection_settings_reads_only_opp_otp_lvp(self) -> None:
        fake_serial = FakeSerial(
            make_field_response(
                _ProtocolType.OVER_POWER_PROTECTION,
                struct.pack("<f", 150.0),
            )
            + make_field_response(
                _ProtocolType.OVER_TEMPERATURE_PROTECTION,
                struct.pack("<f", 80.0),
            )
            + make_field_response(
                _ProtocolType.LOW_VOLTAGE_PROTECTION,
                struct.pack("<f", 5.0),
            )
        )
        with patch(
            "fnirsi_dps150._transport.serial.Serial",
            return_value=fake_serial,
        ):
            with DPS150(port="COM64") as device:
                settings = device.get_protection_settings()

        self.assertEqual(
            settings,
            ProtectionSettings(
                over_power_w=150.0,
                over_temperature_c=80.0,
                low_voltage_v=5.0,
            ),
        )
        self.assertEqual(
            fake_serial.writes,
            [
                _encode_frame(_ProtocolCommand.CONNECT, _ProtocolType.SESSION, b"\x01"),
                _encode_frame(
                    _ProtocolCommand.GET,
                    _ProtocolType.OVER_POWER_PROTECTION,
                ),
                _encode_frame(
                    _ProtocolCommand.GET,
                    _ProtocolType.OVER_TEMPERATURE_PROTECTION,
                ),
                _encode_frame(
                    _ProtocolCommand.GET,
                    _ProtocolType.LOW_VOLTAGE_PROTECTION,
                ),
                _DISCONNECT_FRAME,
            ],
        )

    def test_get_ovp_ocp_thresholds_reads_target_float32_fields(self) -> None:
        fake_serial = FakeSerial(
            make_field_response(
                _ProtocolType.OVER_VOLTAGE_PROTECTION,
                struct.pack("<f", 30.0),
            )
            + make_field_response(
                _ProtocolType.OVER_CURRENT_PROTECTION,
                struct.pack("<f", 5.1),
            )
        )
        with patch(
            "fnirsi_dps150._transport.serial.Serial",
            return_value=fake_serial,
        ):
            with DPS150(port="COM64") as device:
                voltage_threshold = device.get_over_voltage_threshold()
                current_threshold = device.get_over_current_threshold()

        self.assertEqual(voltage_threshold, 30.0)
        self.assertAlmostEqual(current_threshold, 5.1, places=6)
        self.assertEqual(
            fake_serial.writes,
            [
                _encode_frame(_ProtocolCommand.CONNECT, _ProtocolType.SESSION, b"\x01"),
                _encode_frame(
                    _ProtocolCommand.GET,
                    _ProtocolType.OVER_VOLTAGE_PROTECTION,
                ),
                _encode_frame(
                    _ProtocolCommand.GET,
                    _ProtocolType.OVER_CURRENT_PROTECTION,
                ),
                _DISCONNECT_FRAME,
            ],
        )

    def test_get_ovp_ocp_thresholds_rejects_negative_values(self) -> None:
        for type_id, getter in (
            (
                _ProtocolType.OVER_VOLTAGE_PROTECTION,
                DPS150.get_over_voltage_threshold,
            ),
            (
                _ProtocolType.OVER_CURRENT_PROTECTION,
                DPS150.get_over_current_threshold,
            ),
        ):
            with self.subTest(type_id=type_id):
                fake_serial = FakeSerial(
                    make_field_response(type_id, struct.pack("<f", -1.0))
                )
                with patch(
                    "fnirsi_dps150._transport.serial.Serial",
                    return_value=fake_serial,
                ):
                    with DPS150(port="COM64") as device:
                        with self.assertRaises(DPS150ProtocolError):
                            getter(device)

                self.assertEqual(
                    fake_serial.writes,
                    [
                        _encode_frame(
                            _ProtocolCommand.CONNECT,
                            _ProtocolType.SESSION,
                            b"\x01",
                        ),
                        _encode_frame(_ProtocolCommand.GET, type_id),
                        _DISCONNECT_FRAME,
                    ],
                )

    def test_set_ovp_ocp_thresholds_write_float32_only_when_output_is_off(self) -> None:
        for setter, type_id, value in (
            (DPS150.set_over_voltage_threshold, 209, 29.5),
            (DPS150.set_over_current_threshold, 210, 5.0),
        ):
            for enabled in (False, True):
                with self.subTest(type_id=type_id, enabled=enabled):
                    fake_serial = FakeSerial(
                        make_status_response(output_enabled=enabled)
                    )
                    with patch(
                        "fnirsi_dps150._transport.serial.Serial",
                        return_value=fake_serial,
                    ):
                        with DPS150(port="COM64") as device:
                            if enabled:
                                with self.assertRaises(DPS150Error):
                                    setter(device, value)
                            else:
                                setter(device, value)
                    expected = [_encode_frame(_ProtocolCommand.GET, 255)]
                    if not enabled:
                        expected.append(
                            _encode_frame(
                                _ProtocolCommand.SET, type_id, struct.pack("<f", value)
                            )
                        )
                    expected.append(_DISCONNECT_FRAME)
                    self.assertEqual(fake_serial.writes[1:], expected)

    def test_set_ovp_ocp_thresholds_reject_invalid_values_before_io(self) -> None:
        for setter in (
            DPS150.set_over_voltage_threshold,
            DPS150.set_over_current_threshold,
        ):
            for value in (0.0, -1.0, float("nan"), 1e40, True):
                with self.subTest(setter=setter.__name__, value=value):
                    with self.assertRaises(ValueError):
                        setter(DPS150(port="COM64"), value)

    def test_set_protection_settings_requires_output_off_and_writes_only_opp_otp_lvp(
        self,
    ) -> None:
        settings = ProtectionSettings(149.5, 79.5, 5.1)
        fake_serial = FakeSerial(make_status_response())
        with patch(
            "fnirsi_dps150._transport.serial.Serial",
            return_value=fake_serial,
        ):
            with DPS150(port="COM64") as device:
                device.set_protection_settings(settings)

        self.assertEqual(
            fake_serial.writes,
            [
                _encode_frame(_ProtocolCommand.CONNECT, _ProtocolType.SESSION, b"\x01"),
                _encode_frame(_ProtocolCommand.GET, _ProtocolType.STATUS),
                _encode_frame(
                    _ProtocolCommand.SET,
                    _ProtocolType.OVER_POWER_PROTECTION,
                    struct.pack("<f", 149.5),
                ),
                _encode_frame(
                    _ProtocolCommand.SET,
                    _ProtocolType.OVER_TEMPERATURE_PROTECTION,
                    struct.pack("<f", 79.5),
                ),
                _encode_frame(
                    _ProtocolCommand.SET,
                    _ProtocolType.LOW_VOLTAGE_PROTECTION,
                    struct.pack("<f", 5.1),
                ),
                _DISCONNECT_FRAME,
            ],
        )

    def test_set_protection_settings_surfaces_failure_midway_through_writes(self) -> None:
        write_error = OSError("temperature protection write failed")
        fake_serial = FakeSerial(
            make_status_response(),
            write_error=write_error,
            write_error_at=4,
        )
        with patch(
            "fnirsi_dps150._transport.serial.Serial",
            return_value=fake_serial,
        ):
            with DPS150(port="COM64") as device:
                with self.assertRaises(DPS150CommunicationError) as raised:
                    device.set_protection_settings(
                        ProtectionSettings(149.5, 79.5, 5.1)
                    )

        self.assertIs(raised.exception.__cause__, write_error)
        self.assertEqual(
            fake_serial.writes,
            [
                _encode_frame(_ProtocolCommand.CONNECT, _ProtocolType.SESSION, b"\x01"),
                _encode_frame(_ProtocolCommand.GET, _ProtocolType.STATUS),
                _encode_frame(
                    _ProtocolCommand.SET,
                    _ProtocolType.OVER_POWER_PROTECTION,
                    struct.pack("<f", 149.5),
                ),
                _DISCONNECT_FRAME,
            ],
        )

    def test_set_protection_settings_rejects_output_on_and_invalid_values(self) -> None:
        fake_serial = FakeSerial(make_status_response(output_enabled=1))
        with patch(
            "fnirsi_dps150._transport.serial.Serial",
            return_value=fake_serial,
        ):
            with DPS150(port="COM64") as device:
                with self.assertRaises(DPS150Error):
                    device.set_protection_settings(ProtectionSettings(150.0, 80.0, 5.0))

        self.assertEqual(
            fake_serial.writes,
            [
                _encode_frame(_ProtocolCommand.CONNECT, _ProtocolType.SESSION, b"\x01"),
                _encode_frame(_ProtocolCommand.GET, _ProtocolType.STATUS),
                _DISCONNECT_FRAME,
            ],
        )
        for settings in (
            object(),
            ProtectionSettings(-1.0, 80.0, 5.0),
            ProtectionSettings(150.0, float("nan"), 5.0),
        ):
            with self.subTest(settings=settings):
                with self.assertRaises(ValueError):
                    DPS150(port="COM64").set_protection_settings(settings)

    def test_get_preset_reads_first_and_last_slot_without_loading(self) -> None:
        fake_serial = FakeSerial(
            make_field_response(
                _ProtocolType.PRESET_1_VOLTAGE,
                struct.pack("<f", 5.0),
            )
            + make_field_response(
                _ProtocolType.PRESET_1_CURRENT,
                struct.pack("<f", 1.0),
            )
            + make_field_response(
                _ProtocolType.PRESET_6_VOLTAGE,
                struct.pack("<f", 5.5),
            )
            + make_field_response(
                _ProtocolType.PRESET_6_CURRENT,
                struct.pack("<f", 1.5),
            )
        )
        with patch(
            "fnirsi_dps150._transport.serial.Serial",
            return_value=fake_serial,
        ):
            with DPS150(port="COM64") as device:
                first = device.get_preset(1)
                last = device.get_preset(6)

        self.assertEqual(first, Preset(voltage=5.0, current=1.0))
        self.assertEqual(last, Preset(voltage=5.5, current=1.5))
        self.assertEqual(
            fake_serial.writes,
            [
                _encode_frame(_ProtocolCommand.CONNECT, _ProtocolType.SESSION, b"\x01"),
                _encode_frame(_ProtocolCommand.GET, _ProtocolType.PRESET_1_VOLTAGE),
                _encode_frame(_ProtocolCommand.GET, _ProtocolType.PRESET_1_CURRENT),
                _encode_frame(_ProtocolCommand.GET, _ProtocolType.PRESET_6_VOLTAGE),
                _encode_frame(_ProtocolCommand.GET, _ProtocolType.PRESET_6_CURRENT),
                _DISCONNECT_FRAME,
            ],
        )

    def test_get_preset_rejects_invalid_slot_before_serial_io(self) -> None:
        for slot in (0, 7, True, 1.0):
            with self.subTest(slot=slot):
                with self.assertRaises(ValueError):
                    DPS150(port="COM64").get_preset(slot)

    def test_get_preset_rejects_negative_values(self) -> None:
        fake_serial = FakeSerial(
            make_field_response(
                _ProtocolType.PRESET_1_VOLTAGE,
                struct.pack("<f", -1.0),
            )
            + make_field_response(
                _ProtocolType.PRESET_1_CURRENT,
                struct.pack("<f", 1.0),
            )
        )
        with patch(
            "fnirsi_dps150._transport.serial.Serial",
            return_value=fake_serial,
        ):
            with DPS150(port="COM64") as device:
                with self.assertRaises(DPS150ProtocolError):
                    device.get_preset(1)

    def test_set_preset_writes_slot_fields_without_changing_active_output(self) -> None:
        fake_serial = FakeSerial(make_status_response())
        with patch(
            "fnirsi_dps150._transport.serial.Serial",
            return_value=fake_serial,
        ):
            with DPS150(port="COM64") as device:
                device.set_preset(1, Preset(voltage=5.25, current=1.25))

        self.assertEqual(
            fake_serial.writes,
            [
                _encode_frame(_ProtocolCommand.CONNECT, _ProtocolType.SESSION, b"\x01"),
                _encode_frame(_ProtocolCommand.GET, _ProtocolType.STATUS),
                _encode_frame(
                    _ProtocolCommand.SET,
                    _ProtocolType.PRESET_1_VOLTAGE,
                    struct.pack("<f", 5.25),
                ),
                _encode_frame(
                    _ProtocolCommand.SET,
                    _ProtocolType.PRESET_1_CURRENT,
                    struct.pack("<f", 1.25),
                ),
                _DISCONNECT_FRAME,
            ],
        )

    def test_set_preset_surfaces_failure_on_second_stored_field_write(self) -> None:
        write_error = OSError("preset current write failed")
        fake_serial = FakeSerial(
            make_status_response(),
            write_error=write_error,
            write_error_at=4,
        )
        with patch(
            "fnirsi_dps150._transport.serial.Serial",
            return_value=fake_serial,
        ):
            with DPS150(port="COM64") as device:
                with self.assertRaises(DPS150CommunicationError) as raised:
                    device.set_preset(1, Preset(voltage=5.25, current=1.25))

        self.assertIs(raised.exception.__cause__, write_error)
        self.assertEqual(
            fake_serial.writes,
            [
                _encode_frame(_ProtocolCommand.CONNECT, _ProtocolType.SESSION, b"\x01"),
                _encode_frame(_ProtocolCommand.GET, _ProtocolType.STATUS),
                _encode_frame(
                    _ProtocolCommand.SET,
                    _ProtocolType.PRESET_1_VOLTAGE,
                    struct.pack("<f", 5.25),
                ),
                _DISCONNECT_FRAME,
            ],
        )

    def test_set_preset_rejects_output_on_and_values_over_device_limits(self) -> None:
        for response, preset, error_type in (
            (make_status_response(output_enabled=1), Preset(5.0, 1.0), DPS150Error),
            (make_status_response(), Preset(5.0, 5.11), ValueError),
        ):
            with self.subTest(error_type=error_type.__name__):
                fake_serial = FakeSerial(response)
                with patch(
                    "fnirsi_dps150._transport.serial.Serial",
                    return_value=fake_serial,
                ):
                    with DPS150(port="COM64") as device:
                        with self.assertRaises(error_type):
                            device.set_preset(1, preset)

                self.assertEqual(
                    fake_serial.writes,
                    [
                        _encode_frame(
                            _ProtocolCommand.CONNECT,
                            _ProtocolType.SESSION,
                            b"\x01",
                        ),
                        _encode_frame(_ProtocolCommand.GET, _ProtocolType.STATUS),
                        _DISCONNECT_FRAME,
                    ],
                )

    def test_get_system_settings_reads_brightness_volume_and_metering(self) -> None:
        fake_serial = FakeSerial(
            make_field_response(_ProtocolType.BRIGHTNESS, b"\x0e")
            + make_field_response(_ProtocolType.VOLUME, b"\x02")
            + make_field_response(_ProtocolType.METERING_ENABLED, b"\x01")
        )
        with patch(
            "fnirsi_dps150._transport.serial.Serial",
            return_value=fake_serial,
        ):
            with DPS150(port="COM64") as device:
                settings = device.get_system_settings()

        self.assertEqual(
            settings,
            SystemSettings(brightness=14, metering_enabled=True, volume=2),
        )
        self.assertEqual(
            fake_serial.writes,
            [
                _encode_frame(_ProtocolCommand.CONNECT, _ProtocolType.SESSION, b"\x01"),
                _encode_frame(_ProtocolCommand.GET, _ProtocolType.BRIGHTNESS),
                _encode_frame(_ProtocolCommand.GET, _ProtocolType.VOLUME),
                _encode_frame(_ProtocolCommand.GET, _ProtocolType.METERING_ENABLED),
                _DISCONNECT_FRAME,
            ],
        )

    def test_get_system_settings_rejects_invalid_field_values(self) -> None:
        invalid_responses = (
            make_field_response(_ProtocolType.BRIGHTNESS, b"\x0f")
            + make_field_response(_ProtocolType.VOLUME, b"\x00")
            + make_field_response(_ProtocolType.METERING_ENABLED, b"\x00"),
            make_field_response(_ProtocolType.BRIGHTNESS, b"\x0e")
            + make_field_response(_ProtocolType.VOLUME, b"\x0b")
            + make_field_response(_ProtocolType.METERING_ENABLED, b"\x00"),
            make_field_response(_ProtocolType.BRIGHTNESS, b"\x0e")
            + make_field_response(_ProtocolType.VOLUME, b"")
            + make_field_response(_ProtocolType.METERING_ENABLED, b"\x00"),
            make_field_response(_ProtocolType.BRIGHTNESS, b"\x0e")
            + make_field_response(_ProtocolType.VOLUME, b"\x00")
            + make_field_response(_ProtocolType.METERING_ENABLED, b"\x02"),
            make_field_response(_ProtocolType.BRIGHTNESS, b"")
            + make_field_response(_ProtocolType.VOLUME, b"\x00")
            + make_field_response(_ProtocolType.METERING_ENABLED, b"\x00"),
            make_field_response(_ProtocolType.BRIGHTNESS, b"\x0e")
            + make_field_response(_ProtocolType.VOLUME, b"\x00")
            + make_field_response(_ProtocolType.METERING_ENABLED, b""),
        )
        for response in invalid_responses:
            with self.subTest(response=response):
                fake_serial = FakeSerial(response)
                with patch(
                    "fnirsi_dps150._transport.serial.Serial",
                    return_value=fake_serial,
                ):
                    with DPS150(port="COM64") as device:
                        with self.assertRaises(DPS150ProtocolError):
                            device.get_system_settings()

    def test_get_system_settings_fails_fast_on_invalid_brightness(self) -> None:
        for payload in (b"", b"\x0f"):
            with self.subTest(payload=payload):
                fake_serial = FakeSerial(
                    make_field_response(_ProtocolType.BRIGHTNESS, payload)
                )
                with patch(
                    "fnirsi_dps150._transport.serial.Serial",
                    return_value=fake_serial,
                ):
                    with DPS150(port="COM64") as device:
                        with self.assertRaises(DPS150ProtocolError):
                            device.get_system_settings()

                self.assertEqual(
                    fake_serial.writes,
                    [
                        _encode_frame(
                            _ProtocolCommand.CONNECT,
                            _ProtocolType.SESSION,
                            b"\x01",
                        ),
                        _encode_frame(_ProtocolCommand.GET, _ProtocolType.BRIGHTNESS),
                        _DISCONNECT_FRAME,
                    ],
                )

    def test_system_setting_writes_require_output_off_for_brightness_only(self) -> None:
        fake_serial = FakeSerial(make_status_response())
        with patch(
            "fnirsi_dps150._transport.serial.Serial",
            return_value=fake_serial,
        ):
            with DPS150(port="COM64") as device:
                device.set_brightness(14)
                device.set_metering_enabled(True)

        self.assertEqual(
            fake_serial.writes,
            [
                _encode_frame(_ProtocolCommand.CONNECT, _ProtocolType.SESSION, b"\x01"),
                _encode_frame(_ProtocolCommand.GET, _ProtocolType.STATUS),
                _encode_frame(
                    _ProtocolCommand.SET,
                    _ProtocolType.BRIGHTNESS,
                    b"\x0e",
                ),
                _encode_frame(
                    _ProtocolCommand.SET,
                    _ProtocolType.METERING_ENABLED,
                    b"\x01",
                ),
                _DISCONNECT_FRAME,
            ],
        )

    def test_system_setting_writes_reject_invalid_values_without_writing(self) -> None:
        fake_serial = FakeSerial()
        with patch(
            "fnirsi_dps150._transport.serial.Serial",
            return_value=fake_serial,
        ):
            with DPS150(port="COM64") as device:
                for brightness in (True, -1, 15, 1.5):
                    with self.subTest(brightness=brightness):
                        with self.assertRaises(ValueError):
                            device.set_brightness(brightness)
                with self.assertRaises(ValueError):
                    device.set_metering_enabled(1)

        self.assertEqual(
            fake_serial.writes,
            [
                _encode_frame(_ProtocolCommand.CONNECT, _ProtocolType.SESSION, b"\x01"),
                _DISCONNECT_FRAME,
            ],
        )

    def test_brightness_rejects_output_on_while_metering_allows_it(self) -> None:
        fake_serial = FakeSerial(make_status_response(output_enabled=1))
        with patch(
            "fnirsi_dps150._transport.serial.Serial",
            return_value=fake_serial,
        ):
            with DPS150(port="COM64") as device:
                with self.assertRaises(DPS150Error):
                    device.set_brightness(9)
                device.set_metering_enabled(False)

        self.assertEqual(
            fake_serial.writes,
            [
                _encode_frame(_ProtocolCommand.CONNECT, _ProtocolType.SESSION, b"\x01"),
                _encode_frame(_ProtocolCommand.GET, _ProtocolType.STATUS),
                _encode_frame(
                    _ProtocolCommand.SET,
                    _ProtocolType.METERING_ENABLED,
                    b"\x00",
                ),
                _DISCONNECT_FRAME,
            ],
        )

    def test_setpoints_send_float32_without_output_control(self) -> None:
        fake_serial = FakeSerial(make_status_response() * 2)
        with patch(
            "fnirsi_dps150._transport.serial.Serial",
            return_value=fake_serial,
        ):
            with DPS150(port="COM64") as device:
                device.set_voltage(3.25)
                device.set_current(0.75)

        self.assertEqual(
            fake_serial.writes,
            [
                _encode_frame(0xC1, 0x00, b"\x01"),
                _encode_frame(0xA1, 0xFF),
                _encode_frame(0xB1, 193, struct.pack("<f", 3.25)),
                _encode_frame(0xA1, 0xFF),
                _encode_frame(0xB1, 194, struct.pack("<f", 0.75)),
                _DISCONNECT_FRAME,
            ],
        )

    def test_setpoint_accepts_float32_value_matching_reported_limit(self) -> None:
        fake_serial = FakeSerial(make_status_response(current_limit=5.1))
        with patch(
            "fnirsi_dps150._transport.serial.Serial",
            return_value=fake_serial,
        ):
            with DPS150(port="COM64") as device:
                device.set_current(5.1)

        self.assertEqual(
            fake_serial.writes,
            [
                _encode_frame(0xC1, 0x00, b"\x01"),
                _encode_frame(0xA1, 0xFF),
                _encode_frame(0xB1, 194, struct.pack("<f", 5.1)),
                _DISCONNECT_FRAME,
            ],
        )

    def test_setpoints_reject_invalid_values_before_writing(self) -> None:
        invalid_values = (
            -1.0,
            float("nan"),
            float("inf"),
            1e100,
            1e-100,
            10**1000,
            True,
            "1.0",
        )
        fake_serial = FakeSerial()
        with patch(
            "fnirsi_dps150._transport.serial.Serial",
            return_value=fake_serial,
        ):
            with DPS150(port="COM64") as device:
                for value in invalid_values:
                    with self.subTest(value_type=type(value).__name__):
                        with self.assertRaises(ValueError):
                            device.set_voltage(value)
                        with self.assertRaises(ValueError):
                            device.set_current(value)

        self.assertEqual(
            fake_serial.writes,
            [_encode_frame(0xC1, 0x00, b"\x01"), _DISCONNECT_FRAME],
        )

    def test_setpoints_above_reported_limits_are_rejected(self) -> None:
        fake_serial = FakeSerial(make_status_response() * 2)
        with patch(
            "fnirsi_dps150._transport.serial.Serial",
            return_value=fake_serial,
        ):
            with DPS150(port="COM64") as device:
                with self.assertRaises(ValueError):
                    device.set_voltage(20.01)
                with self.assertRaises(ValueError):
                    device.set_current(5.11)

        self.assertEqual(
            fake_serial.writes,
            [
                _encode_frame(0xC1, 0x00, b"\x01"),
                _encode_frame(0xA1, 0xFF),
                _encode_frame(0xA1, 0xFF),
                _DISCONNECT_FRAME,
            ],
        )

    def test_output_control_requires_explicit_bool_and_is_separate(self) -> None:
        fake_serial = FakeSerial()
        with patch(
            "fnirsi_dps150._transport.serial.Serial",
            return_value=fake_serial,
        ):
            with DPS150(port="COM64") as device:
                device.set_output(False)
                device.set_output(True)
                with self.assertRaises(ValueError):
                    device.set_output(1)

        self.assertEqual(
            fake_serial.writes,
            [
                _encode_frame(0xC1, 0x00, b"\x01"),
                _encode_frame(0xB1, 219, b"\x00"),
                _encode_frame(0xB1, 219, b"\x01"),
                _DISCONNECT_FRAME,
            ],
        )

    def test_get_status_rejects_malformed_response_frame(self) -> None:
        response = bytearray(make_status_response())
        response[-1] ^= 1
        fake_serial = FakeSerial(bytes(response))
        with patch(
            "fnirsi_dps150._transport.serial.Serial",
            return_value=fake_serial,
        ):
            with DPS150(port="COM64") as device:
                with self.assertRaises(DPS150ProtocolError):
                    device.get_status()

    def test_get_status_reports_timeout(self) -> None:
        telemetry = _encode_frame(0xA1, 195, bytes(12), header=0xF0)
        fake_serial = FakeSerial(telemetry)
        with patch(
            "fnirsi_dps150._transport.serial.Serial",
            return_value=fake_serial,
        ):
            device = DPS150(port="COM64", timeout=0.1)
            device.open()
            with self.assertRaises(DPS150TimeoutError):
                device.get_status()
            device.close()

        self.assertEqual(
            fake_serial.writes,
            [
                _encode_frame(0xC1, 0x00, b"\x01"),
                _encode_frame(0xA1, 0xFF),
                _DISCONNECT_FRAME,
            ],
        )

    def test_serial_read_failures_are_wrapped_and_timeout_is_restored(self) -> None:
        for read_error in (
            serial.SerialException("read failed"),
            OSError("read failed"),
        ):
            with self.subTest(error_type=type(read_error).__name__):
                fake_serial = FakeSerial(read_error=read_error)
                with patch(
                    "fnirsi_dps150._transport.serial.Serial",
                    return_value=fake_serial,
                ):
                    with self.assertRaises(DPS150CommunicationError) as raised:
                        with DPS150(port="COM64", timeout=0.25) as device:
                            device.get_status()

                self.assertIs(raised.exception.__cause__, read_error)
                self.assertEqual(fake_serial.timeout, 0.25)

    def test_open_failure_preserves_serial_exception(self) -> None:
        with patch(
            "fnirsi_dps150._transport.serial.Serial",
            side_effect=serial.SerialException("port unavailable"),
        ):
            with self.assertRaises(DPS150CommunicationError) as raised:
                DPS150(port="COM64").open()

        self.assertIsInstance(raised.exception.__cause__, serial.SerialException)

    def test_session_handshake_failure_closes_serial_port(self) -> None:
        fake_serial = FakeSerial(write_error=OSError("write failed"))
        with patch(
            "fnirsi_dps150._transport.serial.Serial",
            return_value=fake_serial,
        ):
            with self.assertRaises(DPS150CommunicationError):
                DPS150(port="COM64").open()

        self.assertEqual(fake_serial.close_calls, 1)

    def test_status_read_requires_open_connection(self) -> None:
        with self.assertRaises(DPS150ConnectionError):
            DPS150(port="COM64").get_status()

    def test_context_manager_closes_after_body_failure(self) -> None:
        fake_serial = FakeSerial()
        with patch(
            "fnirsi_dps150._transport.serial.Serial",
            return_value=fake_serial,
        ):
            with self.assertRaisesRegex(RuntimeError, "body failure"):
                with DPS150(port="COM64"):
                    raise RuntimeError("body failure")

        self.assertEqual(fake_serial.close_calls, 1)

    def test_context_manager_preserves_body_exception_when_disconnect_fails(self) -> None:
        fake_serial = FakeSerial(
            write_error=OSError("disconnect failed"),
            write_error_at=2,
        )
        with patch(
            "fnirsi_dps150._transport.serial.Serial",
            return_value=fake_serial,
        ):
            with self.assertRaisesRegex(RuntimeError, "body failure"):
                with DPS150(port="COM64"):
                    raise RuntimeError("body failure")

        self.assertEqual(fake_serial.close_calls, 1)

    def test_timeout_must_be_finite_and_positive(self) -> None:
        for timeout in (0, -1, float("inf"), float("nan"), 10**1000):
            with self.subTest(timeout=timeout):
                with self.assertRaises(ValueError):
                    DPS150(port="COM64", timeout=timeout)

    def test_find_ports_filters_and_sorts_dps150_usb_ids(self) -> None:
        ports = [
            SimpleNamespace(device="COM63", vid=0x0403, pid=0x6001),
            SimpleNamespace(device="COM70", vid=0x2E3C, pid=0x5740),
            SimpleNamespace(device="COM1", vid=None, pid=None),
            SimpleNamespace(device="COM64", vid=0x2E3C, pid=0x5740),
        ]
        with patch(
            "fnirsi_dps150.device.serial.tools.list_ports.comports",
            return_value=ports,
        ):
            self.assertEqual(find_ports(), ("COM64", "COM70"))

    def test_construction_by_serial_number_resolves_vid_2e3c_port_without_serial_io(self) -> None:
        ports = [
            SimpleNamespace(
                device="COM63",
                vid=0x0403,
                pid=0x6001,
                serial_number="10F5D04E4486",
                hwid="USB VID:PID=0403:6001 SER=10F5D04E4486",
            ),
            SimpleNamespace(
                device="COM64",
                vid=0x2E3C,
                pid=0x9999,
                serial_number="10F5D04E4486",
                hwid="USB VID:PID=2E3C:9999 SER=10F5D04E4486",
            ),
        ]
        fake_serial = FakeSerial()
        with (
            patch(
                "fnirsi_dps150.device.serial.tools.list_ports.comports",
                return_value=ports,
            ),
            patch(
                "fnirsi_dps150._transport.serial.Serial",
                return_value=fake_serial,
            ) as serial_factory,
        ):
            device = DPS150(serial_number="  10f5d04e4486  ", timeout=2.5)
            serial_factory.assert_not_called()
            self.assertEqual(device.port, "COM64")
            self.assertEqual(device.serial_number, "10F5D04E4486")
            self.assertFalse(device.is_open)
            self.assertEqual(
                repr(device),
                "DPS150(port='COM64', serial_number='10F5D04E4486', timeout=2.5, is_open=False)",
            )
            device.open()
            device.close()

        self.assertEqual(serial_factory.call_args.kwargs["port"], "COM64")
        self.assertEqual(fake_serial.close_calls, 1)

    def test_construction_by_serial_number_falls_back_to_hwid_fields(self) -> None:
        ports = [
            SimpleNamespace(
                device="COM64",
                vid=None,
                pid=None,
                serial_number=None,
                hwid="USB VID:PID=2E3C:5740 SER=10F5D04E4486 LOCATION=1-3",
            ),
        ]
        with (
            patch(
                "fnirsi_dps150.device.serial.tools.list_ports.comports",
                return_value=ports,
            ),
            patch("fnirsi_dps150._transport.serial.Serial") as serial_factory,
        ):
            device = DPS150(serial_number="10F5D04E4486")

        serial_factory.assert_not_called()
        self.assertEqual(device.port, "COM64")
        self.assertEqual(device.serial_number, "10F5D04E4486")

    def test_construction_rejects_missing_both_or_invalid_port_and_serial_number(self) -> None:
        with self.assertRaises(ValueError):
            DPS150()
        with self.assertRaises(ValueError):
            DPS150(port="COM64", serial_number="10F5D04E4486")
        for bad_port in ("", "   ", 123):
            with self.subTest(bad_port=bad_port):
                with self.assertRaises(ValueError):
                    DPS150(port=bad_port)  # type: ignore[arg-type]
        with patch("fnirsi_dps150.device.serial.tools.list_ports.comports") as comports:
            for bad_sn in ("", "   ", 123):
                with self.subTest(bad_sn=bad_sn):
                    with self.assertRaises(ValueError):
                        DPS150(serial_number=bad_sn)  # type: ignore[arg-type]
            with self.assertRaises(ValueError):
                DPS150(serial_number="10F5D04E4486", timeout=-1.0)
        comports.assert_not_called()

    def test_construction_by_serial_number_raises_connection_error_when_missing_or_ambiguous(
        self,
    ) -> None:
        missing_ports = [
            SimpleNamespace(
                device="COM63",
                vid=0x0403,
                pid=0x6001,
                serial_number="10F5D04E4486",
                hwid="USB VID:PID=0403:6001 SER=10F5D04E4486",
            ),
            SimpleNamespace(
                device="COM64",
                vid=0x2E3C,
                pid=0x5740,
                serial_number="OTHER_SERIAL",
                hwid="USB VID:PID=2E3C:5740 SER=OTHER_SERIAL",
            ),
        ]
        with patch(
            "fnirsi_dps150.device.serial.tools.list_ports.comports",
            return_value=missing_ports,
        ):
            with self.assertRaisesRegex(DPS150ConnectionError, "10F5D04E4486"):
                DPS150(serial_number="10F5D04E4486")

        duplicate_ports = [
            SimpleNamespace(
                device="COM65",
                vid=0x2E3C,
                pid=0x5740,
                serial_number="10F5D04E4486",
                hwid="USB VID:PID=2E3C:5740 SER=10F5D04E4486",
            ),
            SimpleNamespace(
                device="COM64",
                vid=0x2E3C,
                pid=0x5740,
                serial_number="10F5D04E4486",
                hwid="USB VID:PID=2E3C:5740 SER=10F5D04E4486",
            ),
        ]
        with patch(
            "fnirsi_dps150.device.serial.tools.list_ports.comports",
            return_value=duplicate_ports,
        ):
            with self.assertRaisesRegex(DPS150ConnectionError, "COM64, COM65"):
                DPS150(serial_number="10F5D04E4486")

    def test_exchange_flushes_stale_input_buffer_and_wraps_flush_errors(self) -> None:
        stale = b"\xf0\xa1\xc0\x04\x00\x00\x00\x00\xc4"
        fake_serial = FakeSerial(
            make_status_response(),
            stale_prefix=stale,
        )
        with patch(
            "fnirsi_dps150._transport.serial.Serial",
            return_value=fake_serial,
        ):
            with DPS150(port="COM64") as device:
                status = device.get_status()

        self.assertEqual(status.set_voltage, 12.0)
        self.assertEqual(fake_serial.reset_input_buffer_calls, 1)
        self.assertEqual(len(fake_serial.stale_prefix), 0)

        for flush_error in (
            serial.SerialException("flush failed"),
            OSError("flush failed"),
        ):
            with self.subTest(error_type=type(flush_error).__name__):
                failing_serial = FakeSerial(reset_input_error=flush_error)
                with patch(
                    "fnirsi_dps150._transport.serial.Serial",
                    return_value=failing_serial,
                ):
                    with self.assertRaises(DPS150CommunicationError) as raised:
                        with DPS150(port="COM64") as device:
                            device.get_status()
                self.assertIs(raised.exception.__cause__, flush_error)

    def test_read_frame_resynchronizes_past_non_header_bytes(self) -> None:
        fake_serial = FakeSerial(
            b"\x01\x02\xff\x99" + make_status_response(),
            max_read_size=1,
        )
        with patch(
            "fnirsi_dps150._transport.serial.Serial",
            return_value=fake_serial,
        ):
            with DPS150(port="COM64") as device:
                status = device.get_status()

        self.assertEqual(status.set_voltage, 12.0)

    def test_get_protection_status_maps_verified_and_unknown_codes(self) -> None:
        expected_map = {
            0: ProtectionStatus.NONE,
            1: ProtectionStatus.OVP,
            2: ProtectionStatus.OCP,
            3: ProtectionStatus.OPP,
            4: ProtectionStatus.OTP,
            5: ProtectionStatus.LVP,
            6: None,
            255: None,
        }
        for code, expected in expected_map.items():
            with self.subTest(code=code):
                fake_serial = FakeSerial(make_field_response(220, bytes((code,))))
                with patch(
                    "fnirsi_dps150._transport.serial.Serial",
                    return_value=fake_serial,
                ):
                    with DPS150(port="COM64") as device:
                        self.assertEqual(device.get_protection_status(), expected)

    def test_get_protection_limits_reads_and_validates_ceilings(self) -> None:
        responses = (
            make_field_response(228, struct.pack("<f", 30.0))
            + make_field_response(229, struct.pack("<f", 5.1))
            + make_field_response(230, struct.pack("<f", 150.0))
            + make_field_response(231, struct.pack("<f", 99.0))
            + make_field_response(232, struct.pack("<f", 30.0))
        )
        fake_serial = FakeSerial(responses)
        with patch(
            "fnirsi_dps150._transport.serial.Serial",
            return_value=fake_serial,
        ):
            with DPS150(port="COM64") as device:
                limits = device.get_protection_limits()

        self.assertEqual(limits.over_voltage_v, 30.0)
        self.assertAlmostEqual(limits.over_current_a, 5.1, places=6)
        self.assertEqual(limits.over_power_w, 150.0)
        self.assertEqual(limits.over_temperature_c, 99.0)
        self.assertEqual(limits.low_voltage_v, 30.0)
        self.assertEqual(
            fake_serial.writes,
            [
                _encode_frame(_ProtocolCommand.CONNECT, _ProtocolType.SESSION, b"\x01"),
                _encode_frame(_ProtocolCommand.GET, 228),
                _encode_frame(_ProtocolCommand.GET, 229),
                _encode_frame(_ProtocolCommand.GET, 230),
                _encode_frame(_ProtocolCommand.GET, 231),
                _encode_frame(_ProtocolCommand.GET, 232),
                _DISCONNECT_FRAME,
            ],
        )

        bad_responses = (
            make_field_response(228, struct.pack("<f", -1.0))
            + make_field_response(229, struct.pack("<f", 5.1))
            + make_field_response(230, struct.pack("<f", 150.0))
            + make_field_response(231, struct.pack("<f", 99.0))
            + make_field_response(232, struct.pack("<f", 30.0))
        )
        with patch(
            "fnirsi_dps150._transport.serial.Serial",
            return_value=FakeSerial(bad_responses),
        ):
            with DPS150(port="COM64") as device:
                with self.assertRaises(DPS150ProtocolError):
                    device.get_protection_limits()

    def test_get_snapshot_and_get_presets_decode_full_139_byte_payload(self) -> None:
        presets = ((5.0, 1.0), (9.0, 2.0), (12.0, 3.0), (15.0, 3.5), (20.0, 4.0), (24.0, 5.0))
        fake_serial = FakeSerial(
            make_full_status_response(
                input_voltage=19.95,
                set_voltage=12.0,
                set_current=2.5,
                output_voltage=11.98,
                output_current=1.25,
                output_power=14.975,
                temperature=31.5,
                presets=presets,
                ovp=29.5,
                ocp=5.0,
                opp=140.0,
                otp=75.0,
                lvp=6.0,
                brightness=14,
                volume=2,
                metering_enabled=1,
                capacity_ah=0.125,
                energy_wh=1.5,
                output_enabled=1,
                protection_code=3,
                regulation_mode=0,
                voltage_limit=19.75,
                current_limit=5.1,
            )
            * 2
        )
        with patch(
            "fnirsi_dps150._transport.serial.Serial",
            return_value=fake_serial,
        ):
            with DPS150(port="COM64") as device:
                snapshot = device.get_snapshot()
                preset_tuple = device.get_presets()

        self.assertIsInstance(snapshot, DeviceSnapshot)
        self.assertAlmostEqual(snapshot.input_voltage, 19.95, places=4)
        self.assertEqual(snapshot.set_voltage, 12.0)
        self.assertEqual(snapshot.set_current, 2.5)
        self.assertAlmostEqual(snapshot.measurements.output_voltage, 11.98, places=4)
        self.assertAlmostEqual(snapshot.measurements.output_current, 1.25, places=4)
        self.assertAlmostEqual(snapshot.measurements.output_power, 14.975, places=4)
        self.assertEqual(snapshot.temperature, 31.5)
        self.assertEqual(
            snapshot.presets,
            tuple(Preset(voltage=v, current=i) for v, i in presets),
        )
        self.assertEqual(preset_tuple, snapshot.presets)
        self.assertEqual(snapshot.over_voltage_threshold, 29.5)
        self.assertEqual(snapshot.over_current_threshold, 5.0)
        self.assertEqual(
            snapshot.protection_settings,
            ProtectionSettings(over_power_w=140.0, over_temperature_c=75.0, low_voltage_v=6.0),
        )
        self.assertEqual(
            snapshot.system_settings,
            SystemSettings(brightness=14, metering_enabled=True, volume=2),
        )
        self.assertEqual(
            snapshot.metering,
            MeteringReadings(capacity_ah=0.125, energy_wh=1.5),
        )
        self.assertTrue(snapshot.output_enabled)
        self.assertEqual(snapshot.protection_code, 3)
        self.assertEqual(snapshot.protection_status, ProtectionStatus.OPP)
        self.assertEqual(snapshot.regulation_mode, RegulationMode.CC)
        self.assertEqual(snapshot.voltage_limit, 19.75)
        self.assertAlmostEqual(snapshot.current_limit, 5.1, places=6)
        self.assertIsInstance(snapshot.protection_limits, ProtectionLimits)
        assert snapshot.protection_limits is not None
        self.assertEqual(snapshot.protection_limits.over_voltage_v, 30.0)
        self.assertAlmostEqual(snapshot.protection_limits.over_current_a, 5.1, places=6)
        self.assertEqual(snapshot.protection_limits.over_power_w, 150.0)
        self.assertEqual(snapshot.protection_limits.over_temperature_c, 99.0)
        self.assertEqual(snapshot.protection_limits.low_voltage_v, 30.0)

    def test_get_snapshot_handles_119_byte_payload_and_unknown_protection_code(self) -> None:
        payload = bytearray(119)
        struct.pack_into("<f", payload, 0, 12.0)
        struct.pack_into("<f", payload, 4, 5.0)
        struct.pack_into("<f", payload, 8, 1.0)
        payload[96] = 14
        payload[97] = 1
        payload[98] = 0
        payload[107] = 0
        payload[108] = 6
        payload[109] = 1
        struct.pack_into("<f", payload, 111, 11.8)
        struct.pack_into("<f", payload, 115, 5.1)
        frame = _encode_frame(0xA1, 0xFF, bytes(payload), header=0xF0)

        with patch(
            "fnirsi_dps150._transport.serial.Serial",
            return_value=FakeSerial(frame),
        ):
            with DPS150(port="COM64") as device:
                snapshot = device.get_snapshot()

        self.assertEqual(snapshot.system_settings.brightness, 14)
        self.assertEqual(snapshot.system_settings.volume, 1)
        self.assertEqual(snapshot.metering, MeteringReadings(capacity_ah=0.0, energy_wh=0.0))
        self.assertEqual(snapshot.protection_code, 6)
        self.assertIsNone(snapshot.protection_status)
        self.assertIsNone(snapshot.protection_limits)

    def test_get_snapshot_rejects_invalid_fields(self) -> None:
        bad_cases = (
            make_full_status_response(brightness=15),
            make_full_status_response(volume=11),
            make_full_status_response(metering_enabled=2),
            make_full_status_response(capacity_ah=-0.1),
            make_full_status_response(energy_wh=-0.1),
            make_full_status_response(regulation_mode=2),
            make_full_status_response(input_voltage=-0.5),
            make_full_status_response(ovp_limit=-1.0),
        )
        for response in bad_cases:
            with self.subTest(response_len=len(response)):
                with patch(
                    "fnirsi_dps150._transport.serial.Serial",
                    return_value=FakeSerial(response),
                ):
                    with DPS150(port="COM64") as device:
                        with self.assertRaises(DPS150ProtocolError):
                            device.get_snapshot()

    def test_protection_setters_enforce_device_reported_ceilings(self) -> None:
        fake_serial = FakeSerial(make_full_status_response() * 2)
        with patch(
            "fnirsi_dps150._transport.serial.Serial",
            return_value=fake_serial,
        ):
            with DPS150(port="COM64") as device:
                device.set_over_voltage_threshold(30.0)
                device.set_over_current_threshold(5.1)

        self.assertEqual(
            fake_serial.writes,
            [
                _encode_frame(_ProtocolCommand.CONNECT, _ProtocolType.SESSION, b"\x01"),
                _encode_frame(_ProtocolCommand.GET, _ProtocolType.STATUS),
                _encode_frame(_ProtocolCommand.SET, 209, struct.pack("<f", 30.0)),
                _encode_frame(_ProtocolCommand.GET, _ProtocolType.STATUS),
                _encode_frame(_ProtocolCommand.SET, 210, struct.pack("<f", 5.1)),
                _DISCONNECT_FRAME,
            ],
        )

        over_limit_cases = (
            (DPS150.set_over_voltage_threshold, 30.1),
            (DPS150.set_over_current_threshold, 5.15),
            (DPS150.set_protection_settings, ProtectionSettings(150.1, 80.0, 5.0)),
            (DPS150.set_protection_settings, ProtectionSettings(150.0, 99.1, 5.0)),
            (DPS150.set_protection_settings, ProtectionSettings(150.0, 80.0, 30.1)),
        )
        for setter, arg in over_limit_cases:
            with self.subTest(setter=setter.__name__, arg=arg):
                rejected_serial = FakeSerial(make_full_status_response())
                with patch(
                    "fnirsi_dps150._transport.serial.Serial",
                    return_value=rejected_serial,
                ):
                    with DPS150(port="COM64") as device:
                        with self.assertRaises(ValueError):
                            setter(device, arg)  # type: ignore[arg-type]

                self.assertEqual(
                    rejected_serial.writes,
                    [
                        _encode_frame(
                            _ProtocolCommand.CONNECT,
                            _ProtocolType.SESSION,
                            b"\x01",
                        ),
                        _encode_frame(_ProtocolCommand.GET, _ProtocolType.STATUS),
                        _DISCONNECT_FRAME,
                    ],
                )

    def test_connection_properties_and_repr(self) -> None:
        fake_serial = FakeSerial()
        device = DPS150(port="COM64", timeout=2.5)
        self.assertEqual(device.port, "COM64")
        self.assertEqual(device.timeout, 2.5)
        self.assertFalse(device.is_open)
        self.assertEqual(repr(device), "DPS150(port='COM64', timeout=2.5, is_open=False)")

        with patch("fnirsi_dps150._transport.serial.Serial", return_value=fake_serial):
            device.open()
            self.assertTrue(device.is_open)
            self.assertEqual(
                repr(device),
                "DPS150(port='COM64', timeout=2.5, is_open=True)",
            )
            device.close()
        self.assertFalse(device.is_open)

    def test_set_setpoints_validates_both_limits_before_writing_either(self) -> None:
        fake_serial = FakeSerial(make_status_response(voltage_limit=20.0, current_limit=5.1))
        with patch(
            "fnirsi_dps150._transport.serial.Serial",
            return_value=fake_serial,
        ):
            with DPS150(port="COM64") as device:
                device.set_setpoints(5.0, 1.25)

        self.assertEqual(
            fake_serial.writes,
            [
                _encode_frame(_ProtocolCommand.CONNECT, _ProtocolType.SESSION, b"\x01"),
                _encode_frame(_ProtocolCommand.GET, _ProtocolType.STATUS),
                _encode_frame(
                    _ProtocolCommand.SET,
                    _ProtocolType.VOLTAGE_SETPOINT,
                    struct.pack("<f", 5.0),
                ),
                _encode_frame(
                    _ProtocolCommand.SET,
                    _ProtocolType.CURRENT_SETPOINT,
                    struct.pack("<f", 1.25),
                ),
                _DISCONNECT_FRAME,
            ],
        )

        for voltage, current in ((20.1, 1.0), (5.0, 5.2)):
            with self.subTest(voltage=voltage, current=current):
                rejected_serial = FakeSerial(
                    make_status_response(voltage_limit=20.0, current_limit=5.1)
                )
                with patch(
                    "fnirsi_dps150._transport.serial.Serial",
                    return_value=rejected_serial,
                ):
                    with DPS150(port="COM64") as device:
                        with self.assertRaises(ValueError):
                            device.set_setpoints(voltage, current)
                self.assertEqual(
                    rejected_serial.writes,
                    [
                        _encode_frame(
                            _ProtocolCommand.CONNECT,
                            _ProtocolType.SESSION,
                            b"\x01",
                        ),
                        _encode_frame(_ProtocolCommand.GET, _ProtocolType.STATUS),
                        _DISCONNECT_FRAME,
                    ],
                )

        with self.assertRaises(ValueError):
            DPS150(port="COM64").set_setpoints(-1.0, 1.0)
        with self.assertRaises(ValueError):
            DPS150(port="COM64").set_setpoints(1.0, float("nan"))

    def test_individual_opp_otp_lvp_getters_read_and_reject_negative(self) -> None:
        cases = (
            (
                DPS150.get_over_power_threshold,
                _ProtocolType.OVER_POWER_PROTECTION,
                150.0,
            ),
            (
                DPS150.get_over_temperature_threshold,
                _ProtocolType.OVER_TEMPERATURE_PROTECTION,
                80.0,
            ),
            (
                DPS150.get_low_voltage_threshold,
                _ProtocolType.LOW_VOLTAGE_PROTECTION,
                5.0,
            ),
        )
        for getter, type_id, value in cases:
            with self.subTest(getter=getter.__name__):
                fake_serial = FakeSerial(
                    make_field_response(type_id, struct.pack("<f", value))
                )
                with patch(
                    "fnirsi_dps150._transport.serial.Serial",
                    return_value=fake_serial,
                ):
                    with DPS150(port="COM64") as device:
                        self.assertEqual(getter(device), value)
                self.assertEqual(
                    fake_serial.writes,
                    [
                        _encode_frame(
                            _ProtocolCommand.CONNECT,
                            _ProtocolType.SESSION,
                            b"\x01",
                        ),
                        _encode_frame(_ProtocolCommand.GET, type_id),
                        _DISCONNECT_FRAME,
                    ],
                )

                neg_serial = FakeSerial(
                    make_field_response(type_id, struct.pack("<f", -0.5))
                )
                with patch(
                    "fnirsi_dps150._transport.serial.Serial",
                    return_value=neg_serial,
                ):
                    with DPS150(port="COM64") as device:
                        with self.assertRaises(DPS150ProtocolError):
                            getter(device)

    def test_individual_opp_otp_lvp_setters_validate_and_write(self) -> None:
        cases = (
            (
                DPS150.set_over_power_threshold,
                _ProtocolType.OVER_POWER_PROTECTION,
                149.5,
                150.1,
            ),
            (
                DPS150.set_over_temperature_threshold,
                _ProtocolType.OVER_TEMPERATURE_PROTECTION,
                79.5,
                99.1,
            ),
            (
                DPS150.set_low_voltage_threshold,
                _ProtocolType.LOW_VOLTAGE_PROTECTION,
                0.0,
                30.1,
            ),
        )
        for setter, type_id, valid_value, over_limit in cases:
            with self.subTest(setter=setter.__name__):
                for bad in (-1.0, float("nan"), True):
                    with self.assertRaises(ValueError):
                        setter(DPS150(port="COM64"), bad)  # type: ignore[arg-type]

                on_serial = FakeSerial(make_full_status_response(output_enabled=1))
                with patch(
                    "fnirsi_dps150._transport.serial.Serial",
                    return_value=on_serial,
                ):
                    with DPS150(port="COM64") as device:
                        with self.assertRaises(DPS150Error):
                            setter(device, valid_value)

                over_serial = FakeSerial(make_full_status_response())
                with patch(
                    "fnirsi_dps150._transport.serial.Serial",
                    return_value=over_serial,
                ):
                    with DPS150(port="COM64") as device:
                        with self.assertRaises(ValueError):
                            setter(device, over_limit)
                self.assertEqual(
                    over_serial.writes,
                    [
                        _encode_frame(
                            _ProtocolCommand.CONNECT,
                            _ProtocolType.SESSION,
                            b"\x01",
                        ),
                        _encode_frame(_ProtocolCommand.GET, _ProtocolType.STATUS),
                        _DISCONNECT_FRAME,
                    ],
                )

                ok_serial = FakeSerial(make_full_status_response())
                with patch(
                    "fnirsi_dps150._transport.serial.Serial",
                    return_value=ok_serial,
                ):
                    with DPS150(port="COM64") as device:
                        setter(device, valid_value)
                self.assertEqual(
                    ok_serial.writes,
                    [
                        _encode_frame(
                            _ProtocolCommand.CONNECT,
                            _ProtocolType.SESSION,
                            b"\x01",
                        ),
                        _encode_frame(_ProtocolCommand.GET, _ProtocolType.STATUS),
                        _encode_frame(
                            _ProtocolCommand.SET,
                            type_id,
                            struct.pack("<f", valid_value),
                        ),
                        _DISCONNECT_FRAME,
                    ],
                )

    def test_read_frame_resists_embedded_0xf0_in_truncated_payload(self) -> None:
        # Payload bytes containing 0xF0 (float32 30.0 = 00 00 F0 41) before real frame
        truncated = b"\x00\x00\xf0\x41\x11\x22" + make_status_response()
        fake_serial = FakeSerial(truncated, max_read_size=1)
        with patch(
            "fnirsi_dps150._transport.serial.Serial",
            return_value=fake_serial,
        ):
            with DPS150(port="COM64") as device:
                status = device.get_status()
        self.assertEqual(status.set_voltage, 12.0)

        # Also verify 0xF0 immediately before a valid 0xF0 0xA1 frame resynchronizes cleanly
        repeated_f0 = b"\xf0" + make_status_response()
        fake_serial_2 = FakeSerial(repeated_f0, max_read_size=1)
        with patch(
            "fnirsi_dps150._transport.serial.Serial",
            return_value=fake_serial_2,
        ):
            with DPS150(port="COM64") as device:
                status_2 = device.get_status()
        self.assertEqual(status_2.set_voltage, 12.0)

    def test_transport_close_clears_handle_and_open_preserves_connect_error(self) -> None:
        close_err = OSError("usb unplugged")
        fake_serial = FakeSerial(close_error=close_err)
        transport = _SerialTransport(port="COM64", timeout=1.0)
        with patch("fnirsi_dps150._transport.serial.Serial", return_value=fake_serial):
            transport.open()
        with self.assertRaises(DPS150CommunicationError) as raised:
            transport.close()
        self.assertIs(raised.exception.__cause__, close_err)
        self.assertFalse(transport.is_open)
        transport.close()  # idempotent no-op after failed close
        self.assertEqual(fake_serial.close_calls, 1)

        write_err = OSError("connect write failed")
        failing_serial = FakeSerial(write_error=write_err, close_error=close_err)
        with patch(
            "fnirsi_dps150._transport.serial.Serial",
            return_value=failing_serial,
        ):
            device = DPS150(port="COM64")
            with self.assertRaises(DPS150CommunicationError) as open_raised:
                device.open()
        self.assertIs(open_raised.exception.__cause__, write_err)
        self.assertFalse(device.is_open)

    def test_transport_rejects_invalid_command_gap(self) -> None:
        for bad_gap in (-0.1, float("nan"), float("inf"), True, "0.05"):
            with self.subTest(bad_gap=bad_gap):
                with self.assertRaises(ValueError):
                    _SerialTransport(
                        port="COM64",
                        timeout=1.0,
                        command_gap=bad_gap,  # type: ignore[arg-type]
                    )

    def test_get_metering_reads_and_validates_capacity_and_energy(self) -> None:
        fake_serial = FakeSerial(
            make_field_response(_ProtocolType.OUTPUT_CAPACITY, struct.pack("<f", 0.25))
            + make_field_response(_ProtocolType.OUTPUT_ENERGY, struct.pack("<f", 2.5))
        )
        with patch("fnirsi_dps150._transport.serial.Serial", return_value=fake_serial):
            with DPS150(port="COM64") as device:
                readings = device.get_metering()

        self.assertEqual(readings, MeteringReadings(capacity_ah=0.25, energy_wh=2.5))
        self.assertEqual(
            fake_serial.writes,
            [
                _encode_frame(_ProtocolCommand.CONNECT, _ProtocolType.SESSION, b"\x01"),
                _encode_frame(_ProtocolCommand.GET, _ProtocolType.OUTPUT_CAPACITY),
                _encode_frame(_ProtocolCommand.GET, _ProtocolType.OUTPUT_ENERGY),
                _DISCONNECT_FRAME,
            ],
        )

        bad_responses = (
            make_field_response(_ProtocolType.OUTPUT_CAPACITY, struct.pack("<f", -0.01)),
            make_field_response(_ProtocolType.OUTPUT_CAPACITY, struct.pack("<f", float("nan"))),
            make_field_response(_ProtocolType.OUTPUT_CAPACITY, b"\x00\x00"),
            make_field_response(_ProtocolType.OUTPUT_CAPACITY, struct.pack("<f", 0.0))
            + make_field_response(_ProtocolType.OUTPUT_ENERGY, struct.pack("<f", -0.1)),
        )
        for response in bad_responses:
            with self.subTest(response=response):
                with patch(
                    "fnirsi_dps150._transport.serial.Serial",
                    return_value=FakeSerial(response),
                ):
                    with DPS150(port="COM64") as device:
                        with self.assertRaises(DPS150ProtocolError):
                            device.get_metering()

    def test_reset_metering_preserves_enabled_and_disabled_state(self) -> None:
        for initial_byte, expected_writes in (
            (
                b"\x01",
                [
                    _encode_frame(_ProtocolCommand.CONNECT, _ProtocolType.SESSION, b"\x01"),
                    _encode_frame(_ProtocolCommand.GET, _ProtocolType.METERING_ENABLED),
                    _encode_frame(_ProtocolCommand.SET, _ProtocolType.METERING_ENABLED, b"\x00"),
                    _encode_frame(_ProtocolCommand.SET, _ProtocolType.METERING_ENABLED, b"\x01"),
                    _DISCONNECT_FRAME,
                ],
            ),
            (
                b"\x00",
                [
                    _encode_frame(_ProtocolCommand.CONNECT, _ProtocolType.SESSION, b"\x01"),
                    _encode_frame(_ProtocolCommand.GET, _ProtocolType.METERING_ENABLED),
                    _encode_frame(_ProtocolCommand.SET, _ProtocolType.METERING_ENABLED, b"\x01"),
                    _encode_frame(_ProtocolCommand.SET, _ProtocolType.METERING_ENABLED, b"\x00"),
                    _DISCONNECT_FRAME,
                ],
            ),
        ):
            with self.subTest(initial_byte=initial_byte):
                fake_serial = FakeSerial(
                    make_field_response(_ProtocolType.METERING_ENABLED, initial_byte)
                )
                with patch("fnirsi_dps150._transport.serial.Serial", return_value=fake_serial):
                    with DPS150(port="COM64") as device:
                        device.reset_metering()
                self.assertEqual(fake_serial.writes, expected_writes)

        for bad_byte in (b"", b"\x02"):
            with self.subTest(bad_byte=bad_byte):
                bad_serial = FakeSerial(
                    make_field_response(_ProtocolType.METERING_ENABLED, bad_byte)
                )
                with patch("fnirsi_dps150._transport.serial.Serial", return_value=bad_serial):
                    with DPS150(port="COM64") as device:
                        with self.assertRaises(DPS150ProtocolError):
                            device.reset_metering()
                self.assertEqual(
                    bad_serial.writes,
                    [
                        _encode_frame(_ProtocolCommand.CONNECT, _ProtocolType.SESSION, b"\x01"),
                        _encode_frame(_ProtocolCommand.GET, _ProtocolType.METERING_ENABLED),
                        _DISCONNECT_FRAME,
                    ],
                )

    def test_get_volume_and_set_volume_validate_and_require_output_off(self) -> None:
        fake_serial = FakeSerial(
            make_field_response(_ProtocolType.VOLUME, b"\x00")
            + make_field_response(_ProtocolType.VOLUME, b"\x0a")
            + make_status_response()
        )
        with patch("fnirsi_dps150._transport.serial.Serial", return_value=fake_serial):
            with DPS150(port="COM64") as device:
                self.assertEqual(device.get_volume(), 0)
                self.assertEqual(device.get_volume(), 10)
                device.set_volume(2)
                for invalid_volume in (True, -1, 11, 1.5):
                    with self.subTest(invalid_volume=invalid_volume):
                        with self.assertRaises(ValueError):
                            device.set_volume(invalid_volume)

        self.assertEqual(
            fake_serial.writes,
            [
                _encode_frame(_ProtocolCommand.CONNECT, _ProtocolType.SESSION, b"\x01"),
                _encode_frame(_ProtocolCommand.GET, _ProtocolType.VOLUME),
                _encode_frame(_ProtocolCommand.GET, _ProtocolType.VOLUME),
                _encode_frame(_ProtocolCommand.GET, _ProtocolType.STATUS),
                _encode_frame(_ProtocolCommand.SET, _ProtocolType.VOLUME, b"\x02"),
                _DISCONNECT_FRAME,
            ],
        )

        for bad_payload in (b"", b"\x0b"):
            with self.subTest(bad_payload=bad_payload):
                bad_serial = FakeSerial(
                    make_field_response(_ProtocolType.VOLUME, bad_payload)
                )
                with patch(
                    "fnirsi_dps150._transport.serial.Serial",
                    return_value=bad_serial,
                ):
                    with DPS150(port="COM64") as device:
                        with self.assertRaises(DPS150ProtocolError):
                            device.get_volume()

        output_on_serial = FakeSerial(make_status_response(output_enabled=1))
        with patch(
            "fnirsi_dps150._transport.serial.Serial",
            return_value=output_on_serial,
        ):
            with DPS150(port="COM64") as device:
                with self.assertRaises(DPS150Error):
                    device.set_volume(1)


class TransportPacingTests(unittest.TestCase):
    def test_enforces_command_gap_between_writes_and_before_close(self) -> None:
        clock = [100.0]
        sleeps: list[float] = []

        def fake_monotonic() -> float:
            return clock[0]

        def fake_sleep(seconds: float) -> None:
            sleeps.append(seconds)
            clock[0] += seconds

        fake_serial = FakeSerial(make_full_status_response() * 2)
        with (
            patch("fnirsi_dps150._transport.serial.Serial", return_value=fake_serial),
            patch("fnirsi_dps150._transport.time.monotonic", side_effect=fake_monotonic),
            patch("fnirsi_dps150._transport.time.sleep", side_effect=fake_sleep),
        ):
            with DPS150(port="COM64") as device:
                device.set_preset(1, Preset(5.0, 1.0))
                clock[0] += 0.1
                device.set_protection_settings(ProtectionSettings(150.0, 80.0, 5.0))

        self.assertGreaterEqual(len(sleeps), 5)
        for sleep_seconds in sleeps:
            self.assertAlmostEqual(sleep_seconds, 0.05, places=6)
        self.assertEqual(fake_serial.close_calls, 1)


if __name__ == "__main__":
    unittest.main()
