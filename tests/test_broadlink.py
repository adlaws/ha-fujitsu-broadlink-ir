"""Tests for the Broadlink IR format converter."""

from __future__ import annotations

import base64

import pytest

from fujitsu_ir.broadlink import BroadlinkIR
from fujitsu_ir.const import (
    BIT_MARK,
    BROADLINK_IR_TYPE,
    HEADER_MARK,
    HEADER_SPACE,
    MIN_GAP,
    ONE_SPACE,
    ZERO_SPACE,
)
from fujitsu_ir.protocol import FujitsuAC, FujitsuACState


# =============================================================================
# Broadlink base64 ↔ timings
# =============================================================================


class TestBroadlinkBase64:
    """Tests for base64 encoding/decoding of Broadlink IR codes."""

    def test_decode_rejects_short_data(self) -> None:
        """Raise ValueError when the base64 payload is too short."""
        short = base64.b64encode(b"\x26\x00").decode()
        with pytest.raises(ValueError, match="too short"):
            BroadlinkIR.decode_base64(short)

    def test_decode_rejects_wrong_type(self) -> None:
        """Raise ValueError when byte 0 is not the IR type marker."""
        bad_type = base64.b64encode(b"\xFF\x00\x01\x00\x05").decode()
        with pytest.raises(ValueError, match="Not an IR code"):
            BroadlinkIR.decode_base64(bad_type)

    def test_encode_decode_round_trip(self) -> None:
        """Encode timings to base64, decode back — timings should match closely."""
        original = [HEADER_MARK, HEADER_SPACE, BIT_MARK, ONE_SPACE, BIT_MARK, ZERO_SPACE, BIT_MARK, MIN_GAP]
        encoded = BroadlinkIR.encode_base64(original)
        decoded = BroadlinkIR.decode_base64(encoded)

        # Timings are quantised to ticks, so allow ±1 tick (~30µs) tolerance
        assert len(decoded) == len(original)
        for orig, dec in zip(original, decoded):
            assert abs(orig - dec) < 35, f"Timing mismatch: {orig} vs {dec}"

    def test_extended_length_encoding(self) -> None:
        """Values >255 ticks use the 3-byte extended encoding."""
        large_timing = [10000]  # Much larger than 255 ticks
        encoded = BroadlinkIR.encode_base64(large_timing)
        raw = base64.b64decode(encoded)
        # After the 4-byte header, the first timing byte should be 0x00
        # (extended marker)
        assert raw[4] == 0x00


# =============================================================================
# Timings ↔ protocol bytes
# =============================================================================


class TestTimingsToBytes:
    """Tests for converting raw IR timings to protocol bytes."""

    def test_rejects_short_timings(self) -> None:
        """Raise ValueError when timing data is too short."""
        with pytest.raises(ValueError, match="too short"):
            BroadlinkIR.timings_to_bytes([100, 200])

    def test_rejects_bad_header_mark(self) -> None:
        """Raise ValueError when the header mark is too short."""
        with pytest.raises(ValueError, match="Header mark too short"):
            BroadlinkIR.timings_to_bytes([100, 1574, 448, 390])

    def test_rejects_bad_header_space(self) -> None:
        """Raise ValueError when the header space is too short."""
        with pytest.raises(ValueError, match="Header space too short"):
            BroadlinkIR.timings_to_bytes([3324, 100, 448, 390])

    def test_single_byte_decoding(self) -> None:
        """Decode a timing sequence that represents a single byte."""
        # Encode byte 0xA5 = 10100101 (LSB first: 1,0,1,0,0,1,0,1)
        timings = [HEADER_MARK, HEADER_SPACE]
        for bit_idx in range(8):
            bit = (0xA5 >> bit_idx) & 1
            timings.extend([BIT_MARK, ONE_SPACE if bit else ZERO_SPACE])
        timings.extend([BIT_MARK, MIN_GAP])

        result = BroadlinkIR.timings_to_bytes(timings)
        assert len(result) == 1
        assert result[0] == 0xA5


class TestBytesToTimings:
    """Tests for converting protocol bytes to raw IR timings."""

    def test_single_byte(self) -> None:
        """Encoding a single byte produces header + 8 bit pairs + trailing mark + gap."""
        timings = BroadlinkIR.bytes_to_timings(b"\xFF")
        # 2 (header) + 16 (8 bits × mark/space) + 1 (trailing mark) + 1 (gap) = 20
        assert len(timings) == 20
        assert timings[0] == HEADER_MARK
        assert timings[1] == HEADER_SPACE
        assert timings[-1] == MIN_GAP

    def test_all_ones_byte(self) -> None:
        """0xFF — all spaces should be ONE_SPACE."""
        timings = BroadlinkIR.bytes_to_timings(b"\xFF")
        for i in range(2, 18, 2):
            assert timings[i] == BIT_MARK
            assert timings[i + 1] == ONE_SPACE

    def test_all_zeros_byte(self) -> None:
        """0x00 — all spaces should be ZERO_SPACE."""
        timings = BroadlinkIR.bytes_to_timings(b"\x00")
        for i in range(2, 18, 2):
            assert timings[i] == BIT_MARK
            assert timings[i + 1] == ZERO_SPACE


# =============================================================================
# High-level round-trip: bytes → broadlink → bytes
# =============================================================================


class TestHighLevelRoundTrip:
    """Tests for broadlink_to_bytes and bytes_to_broadlink."""

    def test_short_message_round_trip(self) -> None:
        """7-byte off command survives bytes → broadlink → bytes."""
        ac = FujitsuAC()
        original = ac.encode_off()
        b64 = BroadlinkIR.bytes_to_broadlink(original)
        recovered = BroadlinkIR.broadlink_to_bytes(b64)
        assert recovered == original

    def test_long_message_round_trip(self) -> None:
        """16-byte state command survives bytes → broadlink → bytes."""
        ac = FujitsuAC(FujitsuACState(
            mode=0x01,
            temperature=24.0,
            fan=0x02,
            swing=0x01,
        ))
        original = ac.encode_on()
        b64 = BroadlinkIR.bytes_to_broadlink(original)
        recovered = BroadlinkIR.broadlink_to_bytes(b64)
        assert recovered == original

    def test_all_state_combinations(self) -> None:
        """Spot-check a matrix of states through the Broadlink round-trip."""
        for mode in [0x00, 0x01, 0x04]:
            for temp in [16.0, 24.0, 30.0]:
                for fan in [0x00, 0x02, 0x04]:
                    state = FujitsuACState(
                        mode=mode,
                        temperature=temp,
                        fan=fan,
                    )
                    ac = FujitsuAC(state)
                    original = ac.encode_on()
                    b64 = BroadlinkIR.bytes_to_broadlink(original)
                    recovered = BroadlinkIR.broadlink_to_bytes(b64)
                    assert recovered == original
