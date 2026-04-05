"""Tests for the Home Assistant integration IR codec.

Tests the self-contained ``FujitsuACCodec`` and ``FujitsuACState`` in
``custom_components/fujitsu_ac_ir/ir_codec.py``.  These classes mirror
the standalone library but are packaged for the HA integration.
"""

from __future__ import annotations

import base64
import importlib
import sys
import types
from pathlib import Path

import pytest

# The HA integration's __init__.py imports homeassistant, which isn't
# available in the test environment.  We stub the package so that
# ir_codec.py and const.py can be imported directly.
_CC_ROOT = Path(__file__).resolve().parent.parent / "custom_components"
if str(_CC_ROOT) not in sys.path:
    sys.path.insert(0, str(_CC_ROOT))

# Create a minimal stub package that does NOT execute __init__.py
_pkg = types.ModuleType("fujitsu_ac_ir")
_pkg.__path__ = [str(_CC_ROOT / "fujitsu_ac_ir")]
_pkg.__package__ = "fujitsu_ac_ir"
sys.modules["fujitsu_ac_ir"] = _pkg

# Now import the submodules directly
import fujitsu_ac_ir.const as _const_mod  # noqa: E402
import fujitsu_ac_ir.ir_codec as _codec_mod  # noqa: E402

from fujitsu_ac_ir.const import (
    BROADLINK_IR_TYPE,
    CMD_LONG_STATE,
    CMD_TURN_OFF,
    FAN_AUTO,
    FAN_HIGH,
    FAN_LOW,
    FAN_MED,
    FAN_QUIET,
    HEADER_BYTE0,
    HEADER_BYTE1,
    MAX_TEMP,
    MIN_TEMP,
    MODE_AUTO,
    MODE_COOL,
    MODE_DRY,
    MODE_FAN,
    MODE_HEAT,
    PROTOCOL_ARREW4E,
    PROTOCOL_STANDARD,
    STATE_LENGTH,
    STATE_LENGTH_SHORT,
    SWING_BOTH,
    SWING_HORIZ,
    SWING_OFF,
    SWING_VERT,
    TIMER_MAX,
    TIMER_OFF,
    TIMER_ON,
    TIMER_SLEEP,
    TIMER_STOP,
)
from fujitsu_ac_ir.ir_codec import FujitsuACCodec, FujitsuACState


# =============================================================================
# FujitsuACState defaults
# =============================================================================


class TestIntegrationState:
    """Tests for the integration's FujitsuACState dataclass."""

    def test_defaults_power_off(self) -> None:
        """Integration state defaults to power-off (safe for HA startup)."""
        state = FujitsuACState()
        assert state.power is False

    def test_default_values(self) -> None:
        """Verify all default values."""
        state = FujitsuACState()
        assert state.mode == MODE_COOL
        assert state.temperature == 24.0
        assert state.fan == FAN_AUTO
        assert state.swing == SWING_OFF
        assert state.outside_quiet is False
        assert state.device_id == 0
        assert state.protocol == PROTOCOL_ARREW4E


# =============================================================================
# Encoding
# =============================================================================


class TestCodecEncoding:
    """Tests for FujitsuACCodec encoding methods."""

    def test_build_power_off_is_short(self) -> None:
        """Power-off code should be a 7-byte short message."""
        ir_bytes = FujitsuACCodec.build_power_off()
        assert len(ir_bytes) == STATE_LENGTH_SHORT
        assert ir_bytes[5] == CMD_TURN_OFF

    def test_build_power_on_checksum(self) -> None:
        """Power-on code has a valid checksum."""
        state = FujitsuACState(power=True)
        ir_bytes = FujitsuACCodec.build_power_on(state)
        assert len(ir_bytes) == STATE_LENGTH
        assert (sum(ir_bytes[7:16]) & 0xFF) == 0

    def test_build_command_off(self) -> None:
        """build_command with power=False yields a power-off code."""
        state = FujitsuACState(power=False)
        ir_bytes = FujitsuACCodec.build_command(state)
        assert len(ir_bytes) == STATE_LENGTH_SHORT
        assert ir_bytes[5] == CMD_TURN_OFF

    def test_build_command_on(self) -> None:
        """build_command with power=True yields a full state code."""
        state = FujitsuACState(power=True)
        ir_bytes = FujitsuACCodec.build_command(state)
        assert len(ir_bytes) == STATE_LENGTH
        assert ir_bytes[5] == CMD_LONG_STATE

    @pytest.mark.parametrize(
        ("mode", "expected_bits"),
        [
            (MODE_AUTO, 0x00),
            (MODE_COOL, 0x01),
            (MODE_DRY, 0x02),
            (MODE_FAN, 0x03),
            (MODE_HEAT, 0x04),
        ],
    )
    def test_mode_encoding(self, mode: int, expected_bits: int) -> None:
        """Mode values are encoded correctly."""
        state = FujitsuACState(power=True, mode=mode)
        ir_bytes = FujitsuACCodec.build_power_on(state)
        assert ir_bytes[9] & 0x07 == expected_bits

    @pytest.mark.parametrize(
        ("fan", "expected_bits"),
        [
            (FAN_AUTO, 0x00),
            (FAN_HIGH, 0x01),
            (FAN_MED, 0x02),
            (FAN_LOW, 0x03),
            (FAN_QUIET, 0x04),
        ],
    )
    def test_fan_encoding(self, fan: int, expected_bits: int) -> None:
        """Fan values are encoded correctly."""
        state = FujitsuACState(power=True, fan=fan)
        ir_bytes = FujitsuACCodec.build_power_on(state)
        assert ir_bytes[10] & 0x07 == expected_bits

    @pytest.mark.parametrize(
        ("swing", "expected_bits"),
        [
            (SWING_OFF, 0x00),
            (SWING_VERT, 0x01),
            (SWING_HORIZ, 0x02),
            (SWING_BOTH, 0x03),
        ],
    )
    def test_swing_encoding(self, swing: int, expected_bits: int) -> None:
        """Swing values are encoded correctly."""
        state = FujitsuACState(power=True, swing=swing)
        ir_bytes = FujitsuACCodec.build_power_on(state)
        assert (ir_bytes[10] >> 4) & 0x03 == expected_bits

    def test_outside_quiet_encoding(self) -> None:
        """Outside quiet flag is encoded in byte 14 bit 7."""
        state = FujitsuACState(power=True, outside_quiet=True)
        ir_bytes = FujitsuACCodec.build_power_on(state)
        assert ir_bytes[14] & 0x80 != 0

    def test_outside_quiet_off(self) -> None:
        """Outside quiet flag is clear when disabled."""
        state = FujitsuACState(power=True, outside_quiet=False)
        ir_bytes = FujitsuACCodec.build_power_on(state)
        assert ir_bytes[14] & 0x80 == 0


# =============================================================================
# Temperature encoding in the integration codec
# =============================================================================


class TestCodecTemperature:
    """Tests for temperature encoding in the integration codec."""

    @pytest.mark.parametrize(
        ("temp_c", "expected_raw"),
        [
            (16.0, 16),
            (24.0, 32),
            (30.0, 44),
            (16.5, 17),
        ],
    )
    def test_arrew4e_temperature(self, temp_c: float, expected_raw: int) -> None:
        """ARREW4E temperature formula: raw = (deg C - 8) x 2."""
        state = FujitsuACState(power=True, temperature=temp_c)
        ir_bytes = FujitsuACCodec.build_power_on(state)
        raw = (ir_bytes[8] >> 2) & 0x3F
        assert raw == expected_raw

    def test_temperature_clamped_low(self) -> None:
        """Below-minimum temperatures are clamped."""
        state = FujitsuACState(power=True, temperature=5.0)
        ir_bytes = FujitsuACCodec.build_power_on(state)
        raw = (ir_bytes[8] >> 2) & 0x3F
        expected = int((MIN_TEMP - 8.0) * 2)
        assert raw == expected

    def test_temperature_clamped_high(self) -> None:
        """Above-maximum temperatures are clamped."""
        state = FujitsuACState(power=True, temperature=50.0)
        ir_bytes = FujitsuACCodec.build_power_on(state)
        raw = (ir_bytes[8] >> 2) & 0x3F
        expected = int((MAX_TEMP - 8.0) * 2)
        assert raw == expected


# =============================================================================
# Decoding
# =============================================================================


class TestCodecDecoding:
    """Tests for FujitsuACCodec.decode_bytes."""

    def test_decode_rejects_short(self) -> None:
        """Raise ValueError for data shorter than 7 bytes."""
        with pytest.raises(ValueError, match="too short"):
            FujitsuACCodec.decode_bytes(b"\x14\x63\x00")

    def test_decode_rejects_bad_header(self) -> None:
        """Raise ValueError for invalid header bytes."""
        data = b"\xFF\xFF\x00\x10\x10\x02\xFD"
        with pytest.raises(ValueError, match="Invalid header"):
            FujitsuACCodec.decode_bytes(data)

    def test_decode_rejects_bad_checksum(self) -> None:
        """Raise ValueError for checksum mismatch."""
        state = FujitsuACState(power=True)
        ir_bytes = bytearray(FujitsuACCodec.build_power_on(state))
        ir_bytes[10] ^= 0xFF  # Corrupt
        with pytest.raises(ValueError, match="Checksum"):
            FujitsuACCodec.decode_bytes(bytes(ir_bytes))

    def test_decode_off_command(self) -> None:
        """Decoding a power-off message returns power=False."""
        ir_bytes = FujitsuACCodec.build_power_off()
        state = FujitsuACCodec.decode_bytes(ir_bytes)
        assert state.power is False

    def test_decode_on_command(self) -> None:
        """Decoding a power-on message returns the expected state."""
        original = FujitsuACState(
            power=True,
            mode=MODE_HEAT,
            temperature=28.0,
            fan=FAN_HIGH,
            swing=SWING_VERT,
            outside_quiet=True,
        )
        ir_bytes = FujitsuACCodec.build_power_on(original)
        decoded = FujitsuACCodec.decode_bytes(ir_bytes)

        assert decoded.power is True
        assert decoded.mode == MODE_HEAT
        assert decoded.temperature == 28.0
        assert decoded.fan == FAN_HIGH
        assert decoded.swing == SWING_VERT
        assert decoded.outside_quiet is True


# =============================================================================
# Broadlink conversion and timings
# =============================================================================


class TestCodecBroadlink:
    """Tests for Broadlink format conversion in the integration codec."""

    def test_broadlink_rejects_invalid(self) -> None:
        """Raise ValueError for invalid Broadlink codes."""
        bad = base64.b64encode(b"\xFF\x00\x01\x00\x05").decode()
        with pytest.raises(ValueError, match="Invalid"):
            FujitsuACCodec.broadlink_to_bytes(bad)

    def test_broadlink_round_trip(self) -> None:
        """Encode bytes -> broadlink -> decode -- bytes must match."""
        state = FujitsuACState(
            power=True,
            mode=MODE_COOL,
            temperature=22.5,
            fan=FAN_LOW,
            swing=SWING_HORIZ,
        )
        ir_bytes = FujitsuACCodec.build_power_on(state)
        b64 = FujitsuACCodec.bytes_to_broadlink(ir_bytes)
        decoded_bytes = FujitsuACCodec.broadlink_to_bytes(b64)
        decoded = FujitsuACCodec.decode_bytes(decoded_bytes)

        assert decoded.mode == MODE_COOL
        assert decoded.temperature == 22.5
        assert decoded.fan == FAN_LOW
        assert decoded.swing == SWING_HORIZ

    def test_bytes_to_timings_length(self) -> None:
        """bytes_to_timings returns correct number of timing values."""
        ir_bytes = FujitsuACCodec.build_power_off()
        timings = FujitsuACCodec.bytes_to_timings(ir_bytes)
        # Header (2) + bits (7 bytes x 8 bits x 2 values) + footer (2)
        expected = 2 + (STATE_LENGTH_SHORT * 8 * 2) + 2
        assert len(timings) == expected

    def test_build_command_timings(self) -> None:
        """build_command_timings produces timings matching bytes_to_timings."""
        state = FujitsuACState(power=True)
        timings = FujitsuACCodec.build_command_timings(state)
        ir_bytes = FujitsuACCodec.build_command(state)
        expected = FujitsuACCodec.bytes_to_timings(ir_bytes)
        assert timings == expected


# =============================================================================
# Timer encoding (integration codec)
# =============================================================================


class TestCodecTimerEncoding:
    """Tests for timer encoding in the integration codec."""

    def test_build_off_timer_checksum(self) -> None:
        """Off timer code has a valid checksum."""
        state = FujitsuACState(power=True)
        ir_bytes = FujitsuACCodec.build_off_timer(state, 60)
        assert len(ir_bytes) == STATE_LENGTH
        assert (sum(ir_bytes[7:16]) & 0xFF) == 0

    def test_build_off_timer_encodes_type(self) -> None:
        """Off timer sets timer type to TIMER_OFF in byte 9."""
        state = FujitsuACState(power=True)
        ir_bytes = FujitsuACCodec.build_off_timer(state, 30)
        assert (ir_bytes[9] >> 4) & 0x03 == TIMER_OFF

    def test_build_off_timer_value(self) -> None:
        """Off timer encodes the correct minute value."""
        state = FujitsuACState(power=True)
        ir_bytes = FujitsuACCodec.build_off_timer(state, 30)
        off_timer = (ir_bytes[11] & 0xFF) | ((ir_bytes[12] & 0x07) << 8)
        assert off_timer == 30
        assert bool(ir_bytes[12] & 0x08) is True  # OffTimerEnable

    def test_build_on_timer_value(self) -> None:
        """On timer encodes the correct minute value."""
        state = FujitsuACState(power=True, mode=MODE_COOL, temperature=24.0)
        ir_bytes = FujitsuACCodec.build_on_timer(state, 510)
        assert (ir_bytes[9] >> 4) & 0x03 == TIMER_ON
        on_timer = ((ir_bytes[12] >> 4) & 0x0F) | ((ir_bytes[13] & 0x7F) << 4)
        assert on_timer == 510
        assert bool(ir_bytes[13] & 0x80) is True  # OnTimerEnable

    def test_build_on_timer_max(self) -> None:
        """On timer at maximum (720 minutes / 12 hours)."""
        state = FujitsuACState(power=True)
        ir_bytes = FujitsuACCodec.build_on_timer(state, TIMER_MAX)
        on_timer = ((ir_bytes[12] >> 4) & 0x0F) | ((ir_bytes[13] & 0x7F) << 4)
        assert on_timer == TIMER_MAX

    def test_build_sleep_timer_value(self) -> None:
        """Sleep timer encodes correctly."""
        state = FujitsuACState(power=True)
        ir_bytes = FujitsuACCodec.build_sleep_timer(state, 180)
        assert (ir_bytes[9] >> 4) & 0x03 == TIMER_SLEEP
        off_timer = (ir_bytes[11] & 0xFF) | ((ir_bytes[12] & 0x07) << 8)
        assert off_timer == 180

    def test_build_cancel_timer(self) -> None:
        """Cancel timer produces timer type TIMER_STOP with zero values."""
        state = FujitsuACState(power=True)
        ir_bytes = FujitsuACCodec.build_cancel_timer(state)
        assert (ir_bytes[9] >> 4) & 0x03 == TIMER_STOP
        assert ir_bytes[11] == 0x00
        assert ir_bytes[12] == 0x00
        assert ir_bytes[13] == 0x00

    def test_build_cancel_timer_when_off(self) -> None:
        """Cancel timer with power=False sends a short off command."""
        state = FujitsuACState(power=False)
        ir_bytes = FujitsuACCodec.build_cancel_timer(state)
        assert len(ir_bytes) == STATE_LENGTH_SHORT

    def test_build_off_timer_rejects_zero(self) -> None:
        """Off timer rejects 0 minutes."""
        state = FujitsuACState(power=True)
        with pytest.raises(ValueError, match="1\u2013720"):
            FujitsuACCodec.build_off_timer(state, 0)

    def test_build_off_timer_rejects_over_max(self) -> None:
        """Off timer rejects values over TIMER_MAX."""
        state = FujitsuACState(power=True)
        with pytest.raises(ValueError, match="1\u2013720"):
            FujitsuACCodec.build_off_timer(state, 721)

    def test_build_on_timer_preserves_state(self) -> None:
        """On timer includes mode, temp, fan, swing from the state."""
        state = FujitsuACState(
            power=True,
            mode=MODE_HEAT,
            temperature=28.0,
            fan=FAN_HIGH,
            swing=SWING_HORIZ,
        )
        ir_bytes = FujitsuACCodec.build_on_timer(state, 60)
        decoded = FujitsuACCodec.decode_bytes(ir_bytes)
        assert decoded.mode == MODE_HEAT
        assert decoded.temperature == 28.0
        assert decoded.fan == FAN_HIGH
        assert decoded.swing == SWING_HORIZ


# =============================================================================
# Timer decoding (integration codec)
# =============================================================================


class TestCodecTimerDecoding:
    """Tests for timer decoding in the integration codec."""

    def test_decode_off_timer(self) -> None:
        """Decode an off timer message."""
        state = FujitsuACState(power=True)
        ir_bytes = FujitsuACCodec.build_off_timer(state, 120)
        decoded = FujitsuACCodec.decode_bytes(ir_bytes)
        assert decoded.timer_type == TIMER_OFF
        assert decoded.off_timer_minutes == 120

    def test_decode_on_timer(self) -> None:
        """Decode an on timer message."""
        state = FujitsuACState(power=True)
        ir_bytes = FujitsuACCodec.build_on_timer(state, 450)
        decoded = FujitsuACCodec.decode_bytes(ir_bytes)
        assert decoded.timer_type == TIMER_ON
        assert decoded.on_timer_minutes == 450

    def test_decode_sleep_timer(self) -> None:
        """Decode a sleep timer message."""
        state = FujitsuACState(power=True)
        ir_bytes = FujitsuACCodec.build_sleep_timer(state, 90)
        decoded = FujitsuACCodec.decode_bytes(ir_bytes)
        assert decoded.timer_type == TIMER_SLEEP
        assert decoded.off_timer_minutes == 90
