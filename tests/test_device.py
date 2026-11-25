"""Hardware-free tests for the public device connection and status API."""

import struct
import unittest
from unittest.mock import patch

import serial

from fnirsi_dps150 import DPS150, Measurements
from fnirsi_dps150._protocol import _encode_frame
from fnirsi_dps150.definitions.exceptions import (
    DPS150CommunicationError,
    DPS150ConnectionError,
    DPS150ProtocolError,
    DPS150TimeoutError,
)


class FakeSerial:
    def __init__(
        self,
        response: bytes = b"",
        max_read_size: int = 1024,
        write_error: OSError | None = None,
    ) -> None:
        self.timeout: float | None = 1.0
        self.is_open = True
        self.response = bytearray(response)
        self.max_read_size = max_read_size
        self.writes: list[bytes] = []
        self.close_calls = 0
        self.write_error = write_error

    def write(self, packet: bytes) -> int:
        if self.write_error is not None:
            raise self.write_error
        self.writes.append(packet)
        return len(packet)

    def read(self, count: int) -> bytes:
        if not self.response:
            return b""
        read_size = min(count, self.max_read_size, len(self.response))
        result = bytes(self.response[:read_size])
        del self.response[:read_size]
        return result

    def close(self) -> None:
        self.close_calls += 1
        self.is_open = False


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


def make_measurements_response(
    voltage: float = 12.0,
    current: float = 0.5,
    power: float = 6.0,
) -> bytes:
    payload = struct.pack("<3f", voltage, current, power)
    return _encode_frame(0xA1, 195, payload, header=0xF0)


class DeviceTests(unittest.TestCase):
    def test_construction_does_not_open_serial_port(self) -> None:
        with patch("fnirsi_dps150._transport.serial.Serial") as serial_factory:
            device = DPS150(port="COM64")

        serial_factory.assert_not_called()
        self.assertIsInstance(device, DPS150)

    def test_open_sends_only_session_handshake_and_close_sends_nothing(self) -> None:
        fake_serial = FakeSerial()
        with patch(
            "fnirsi_dps150._transport.serial.Serial",
            return_value=fake_serial,
        ) as serial_factory:
            device = DPS150(port="COM64")
            device.open()
            device.close()

        self.assertEqual(fake_serial.writes, [_encode_frame(0xC1, 0x00, b"\x01")])
        self.assertEqual(fake_serial.close_calls, 1)
        self.assertEqual(serial_factory.call_args.kwargs["baudrate"], 115200)
        self.assertEqual(serial_factory.call_args.kwargs["timeout"], 1.0)
        self.assertFalse(serial_factory.call_args.kwargs["rtscts"])

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

        self.assertEqual(fake_serial.writes, [_encode_frame(0xC1, 0x00, b"\x01")])

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
            ],
        )

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

    def test_timeout_must_be_finite_and_positive(self) -> None:
        for timeout in (0, -1, float("inf"), float("nan"), 10**1000):
            with self.subTest(timeout=timeout):
                with self.assertRaises(ValueError):
                    DPS150(port="COM64", timeout=timeout)


if __name__ == "__main__":
    unittest.main()
