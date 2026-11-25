"""Tests for private serial-frame encoding and decoding."""

import unittest

from fnirsi_dps150._protocol import _decode_frame, _encode_frame
from fnirsi_dps150.definitions.exceptions import DPS150ProtocolError


class ProtocolTests(unittest.TestCase):
    def test_encode_frame_uses_documented_checksum(self) -> None:
        self.assertEqual(
            _encode_frame(0xA1, 0xFF),
            bytes((0xF1, 0xA1, 0xFF, 0, 0xFF)),
        )

    def test_decode_response_frame(self) -> None:
        response = _encode_frame(0xA1, 0xFF, b"\x01", header=0xF0)

        frame = _decode_frame(response)

        self.assertEqual(frame.command, 0xA1)
        self.assertEqual(frame.type_id, 0xFF)
        self.assertEqual(frame.payload, b"\x01")

    def test_decode_rejects_malformed_frames(self) -> None:
        cases = (
            b"\xF0\xA1\xFF\x00",
            b"\xF1\xA1\xFF\x00\xFF",
            b"\xF0\xA1\xFF\x01\x01\x00",
        )
        for packet in cases:
            with self.subTest(packet=packet):
                with self.assertRaises(DPS150ProtocolError):
                    _decode_frame(packet)

    def test_encode_rejects_payload_larger_than_length_field(self) -> None:
        with self.assertRaises(DPS150ProtocolError):
            _encode_frame(0xA1, 0xFF, bytes(256))


if __name__ == "__main__":
    unittest.main()
