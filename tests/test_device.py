"""Hardware-free tests for the public device connection and status API."""

import unittest
from unittest.mock import patch

import serial

from fnirsi_dps150 import DPS150, DeviceStatus
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


def make_status_response(output_enabled: int = 0) -> bytes:
    payload = bytearray(108)
    payload[107] = output_enabled
    return _encode_frame(0xA1, 0xFF, bytes(payload), header=0xF0)


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

        self.assertEqual(status, DeviceStatus(output_enabled=False))
        self.assertEqual(
            fake_serial.writes,
            [
                _encode_frame(0xC1, 0x00, b"\x01"),
                _encode_frame(0xA1, 0xFF),
            ],
        )
        self.assertEqual(fake_serial.close_calls, 1)

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
        fake_serial = FakeSerial()
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
