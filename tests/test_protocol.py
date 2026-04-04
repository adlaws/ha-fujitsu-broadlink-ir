"""Tests for the Fujitsu AC IR protocol encoder/decoder."""

from __future__ import annotations

import pytest

from fujitsu_ir.const import (
    CMD_ECONO,
    CMD_LONG_STATE,
    CMD_POWERFUL,
    CMD_STAY_ON,
    CMD_STEP_HORIZ,
    CMD_STEP_VERT,
    CMD_TOGGLE_SWING_HORIZ,
    CMD_TOGGLE_SWING_VERT,
    CMD_TURN_OFF,
    CMD_TURN_ON,
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
from fujitsu_ir.protocol import FujitsuAC, FujitsuACState, SHORT_COMMANDS


# =============================================================================
# FujitsuACState dataclass
# =============================================================================


class TestFujitsuACState:
    """Tests for the FujitsuACState dataclass."""

    def test_default_values(self) -> None:
        """Verify the defaults produce a sensible power-on state."""
        state = FujitsuACState()
        assert state.power is True
        assert state.mode == MODE_COOL
        assert state.temperature == 24.0
        assert state.fan == FAN_AUTO
        assert state.swing == SWING_OFF
        assert state.outside_quiet is False
        assert state.filter_active is False
        assert state.clean is False
        assert state.device_id == 0
        assert state.protocol == PROTOCOL_ARREW4E

    def test_str_representation(self) -> None:
        """Verify __str__ returns a readable summary."""
        state = FujitsuACState(power=True, mode=MODE_HEAT, temperature=28.0)
        text = str(state)
        assert "ON" in text
        assert "Heat" in text
        assert "28.0" in text


# =============================================================================
# Short command encoding
# =============================================================================


class TestShortCommands:
    """Tests for 7-byte short command encoding."""

    def test_encode_off(self) -> None:
        """Power-off command produces a valid 7-byte message."""
        ac = FujitsuAC()
        data = ac.encode_off()
        assert len(data) == STATE_LENGTH_SHORT
        assert data[0] == HEADER_BYTE0
        assert data[1] == HEADER_BYTE1
        assert data[5] == CMD_TURN_OFF
        assert data[6] == (~CMD_TURN_OFF) & 0xFF

    def test_short_command_inverse_byte(self) -> None:
        """Every short command has byte 6 == ~byte 5."""
        ac = FujitsuAC()
        for cmd in SHORT_COMMANDS:
            ac.command = cmd
            data = ac.encode()
            assert data[6] == (~data[5]) & 0xFF, f"Command 0x{cmd:02X}"

    def test_short_command_length(self) -> None:
        """All short commands produce exactly 7 bytes."""
        ac = FujitsuAC()
        for cmd in SHORT_COMMANDS:
            ac.command = cmd
            data = ac.encode()
            assert len(data) == STATE_LENGTH_SHORT, f"Command 0x{cmd:02X}"

    def test_device_id_in_short_command(self) -> None:
        """Device ID is encoded in bits 5:4 of byte 2."""
        for dev_id in range(4):
            state = FujitsuACState(device_id=dev_id)
            ac = FujitsuAC(state)
            data = ac.encode_off()
            assert (data[2] >> 4) & 0x03 == dev_id

    def test_verify_short_checksum(self) -> None:
        """verify_short_checksum accepts valid short messages."""
        ac = FujitsuAC()
        data = ac.encode_off()
        assert FujitsuAC.verify_short_checksum(data) is True

    def test_verify_short_checksum_rejects_corrupted(self) -> None:
        """verify_short_checksum rejects a corrupted message."""
        ac = FujitsuAC()
        data = bytearray(ac.encode_off())
        data[6] ^= 0xFF  # Corrupt the inverse byte
        assert FujitsuAC.verify_short_checksum(bytes(data)) is False


# =============================================================================
# Long command encoding
# =============================================================================


class TestLongCommands:
    """Tests for 16-byte full state encoding."""

    def test_encode_on_length(self) -> None:
        """Power-on command produces a 16-byte message."""
        ac = FujitsuAC()
        data = ac.encode_on()
        assert len(data) == STATE_LENGTH

    def test_header_bytes(self) -> None:
        """Fixed header bytes are correct."""
        ac = FujitsuAC()
        data = ac.encode_on()
        assert data[0] == HEADER_BYTE0
        assert data[1] == HEADER_BYTE1
        assert data[3] == 0x10
        assert data[4] == 0x10

    def test_long_command_indicator(self) -> None:
        """Byte 5 is 0xFE for full state messages."""
        ac = FujitsuAC()
        data = ac.encode_on()
        assert data[5] == CMD_LONG_STATE

    def test_rest_length(self) -> None:
        """Byte 6 holds the rest-of-message length."""
        ac = FujitsuAC()
        data = ac.encode_on()
        assert data[6] == STATE_LENGTH - 7

    def test_protocol_byte(self) -> None:
        """Byte 7 reflects the protocol version."""
        ac = FujitsuAC(FujitsuACState(protocol=PROTOCOL_ARREW4E))
        assert ac.encode_on()[7] == PROTOCOL_ARREW4E

        ac2 = FujitsuAC(FujitsuACState(protocol=PROTOCOL_STANDARD))
        assert ac2.encode_on()[7] == PROTOCOL_STANDARD

    def test_checksum_valid(self) -> None:
        """Sum of bytes 7–15 is zero mod 256."""
        ac = FujitsuAC()
        data = ac.encode_on()
        assert (sum(data[7:16]) & 0xFF) == 0

    def test_verify_checksum(self) -> None:
        """verify_checksum accepts valid long messages."""
        ac = FujitsuAC()
        data = ac.encode_on()
        assert FujitsuAC.verify_checksum(data) is True

    def test_verify_checksum_rejects_corrupted(self) -> None:
        """verify_checksum rejects a corrupted message."""
        ac = FujitsuAC()
        data = bytearray(ac.encode_on())
        data[10] ^= 0xFF  # Corrupt a data byte
        assert FujitsuAC.verify_checksum(bytes(data)) is False

    def test_power_bit(self) -> None:
        """Power bit (byte 8, bit 0) is set for turn-on commands."""
        ac = FujitsuAC(FujitsuACState(power=True))
        data = ac.encode_on()
        assert data[8] & 0x01 == 1

    def test_arrew4e_bit0_set(self) -> None:
        """ARREW4E protocol always sets bit 0 of byte 14."""
        ac = FujitsuAC(FujitsuACState(protocol=PROTOCOL_ARREW4E))
        data = ac.encode_on()
        assert data[14] & 0x01 == 1

    def test_standard_protocol_bit0_clear(self) -> None:
        """Standard protocol does not set bit 0 of byte 14."""
        ac = FujitsuAC(FujitsuACState(protocol=PROTOCOL_STANDARD))
        data = ac.encode_on()
        assert data[14] & 0x01 == 0

    def test_outside_quiet_bit(self) -> None:
        """Outside quiet flag is byte 14 bit 7."""
        ac = FujitsuAC(FujitsuACState(outside_quiet=True))
        data = ac.encode_on()
        assert data[14] & 0x80 != 0

        ac2 = FujitsuAC(FujitsuACState(outside_quiet=False))
        data2 = ac2.encode_on()
        assert data2[14] & 0x80 == 0

    def test_filter_bit(self) -> None:
        """Filter flag is byte 14 bit 3."""
        ac = FujitsuAC(FujitsuACState(filter_active=True))
        data = ac.encode_on()
        assert data[14] & 0x08 != 0

    def test_clean_bit(self) -> None:
        """Clean flag is byte 9 bit 3."""
        ac = FujitsuAC(FujitsuACState(clean=True))
        data = ac.encode_on()
        assert data[9] & 0x08 != 0


# =============================================================================
# Temperature encoding (ARREW4E protocol 0x31)
# =============================================================================


class TestTemperatureARREW4E:
    """Tests for ARREW4E temperature encoding: raw = (°C - 8) × 2."""

    @pytest.mark.parametrize(
        ("temp_c", "expected_raw"),
        [
            (16.0, 16),   # (16 - 8) * 2 = 16
            (24.0, 32),   # (24 - 8) * 2 = 32
            (30.0, 44),   # (30 - 8) * 2 = 44
            (16.5, 17),   # (16.5 - 8) * 2 = 17
        ],
    )
    def test_temperature_encoding(self, temp_c: float, expected_raw: int) -> None:
        """Temperature encodes correctly in byte 8 bits 7:2."""
        ac = FujitsuAC(FujitsuACState(
            temperature=temp_c,
            protocol=PROTOCOL_ARREW4E,
        ))
        data = ac.encode_on()
        raw = (data[8] >> 2) & 0x3F
        assert raw == expected_raw, f"Temp {temp_c}°C"

    def test_temperature_clamped_low(self) -> None:
        """Temperatures below minimum are clamped to 16°C."""
        ac = FujitsuAC(FujitsuACState(temperature=10.0))
        data = ac.encode_on()
        raw = (data[8] >> 2) & 0x3F
        expected = int((MIN_TEMP - 8.0) * 2)
        assert raw == expected

    def test_temperature_clamped_high(self) -> None:
        """Temperatures above maximum are clamped to 30°C."""
        ac = FujitsuAC(FujitsuACState(temperature=40.0))
        data = ac.encode_on()
        raw = (data[8] >> 2) & 0x3F
        expected = int((MAX_TEMP - 8.0) * 2)
        assert raw == expected


# =============================================================================
# Temperature encoding (Standard protocol 0x30)
# =============================================================================


class TestTemperatureStandard:
    """Tests for standard temperature encoding: raw = (°C - 16) × 4."""

    @pytest.mark.parametrize(
        ("temp_c", "expected_raw"),
        [
            (16.0, 0),    # (16 - 16) * 4 = 0
            (24.0, 32),   # (24 - 16) * 4 = 32
            (30.0, 56),   # (30 - 16) * 4 = 56
        ],
    )
    def test_temperature_encoding(self, temp_c: float, expected_raw: int) -> None:
        """Temperature encodes correctly for standard protocol."""
        ac = FujitsuAC(FujitsuACState(
            temperature=temp_c,
            protocol=PROTOCOL_STANDARD,
        ))
        data = ac.encode_on()
        raw = (data[8] >> 2) & 0x3F
        assert raw == expected_raw


# =============================================================================
# Mode, fan, and swing encoding
# =============================================================================


class TestModeEncoding:
    """Tests for operating mode encoding in byte 9 bits 2:0."""

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
        """Mode value appears in byte 9 bits 2:0."""
        ac = FujitsuAC(FujitsuACState(mode=mode))
        data = ac.encode_on()
        assert data[9] & 0x07 == expected_bits


class TestFanEncoding:
    """Tests for fan speed encoding in byte 10 bits 2:0."""

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
        """Fan value appears in byte 10 bits 2:0."""
        ac = FujitsuAC(FujitsuACState(fan=fan))
        data = ac.encode_on()
        assert data[10] & 0x07 == expected_bits


class TestSwingEncoding:
    """Tests for swing mode encoding in byte 10 bits 5:4."""

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
        """Swing value appears in byte 10 bits 5:4."""
        ac = FujitsuAC(FujitsuACState(swing=swing))
        data = ac.encode_on()
        assert (data[10] >> 4) & 0x03 == expected_bits


# =============================================================================
# Decoding
# =============================================================================


class TestDecoding:
    """Tests for FujitsuAC.from_bytes decoding."""

    def test_decode_rejects_short_data(self) -> None:
        """Raise ValueError if data is too short."""
        with pytest.raises(ValueError, match="too short"):
            FujitsuAC.from_bytes(b"\x14\x63\x00")

    def test_decode_rejects_bad_header(self) -> None:
        """Raise ValueError if the header is wrong."""
        data = b"\xFF\xFF\x00\x10\x10\x02\xFD"
        with pytest.raises(ValueError, match="Invalid header"):
            FujitsuAC.from_bytes(data)

    def test_decode_short_off(self) -> None:
        """Decode a power-off short message."""
        ac = FujitsuAC()
        raw = ac.encode_off()
        decoded = FujitsuAC.from_bytes(raw)
        assert decoded.command == CMD_TURN_OFF
        assert decoded.state.power is False

    def test_decode_short_commands(self) -> None:
        """Decode various short commands."""
        ac = FujitsuAC()
        for cmd in SHORT_COMMANDS:
            ac.command = cmd
            raw = ac.encode()
            decoded = FujitsuAC.from_bytes(raw)
            assert decoded.command == cmd

    def test_decode_long_checksum_error(self) -> None:
        """Raise ValueError on checksum mismatch in long message."""
        ac = FujitsuAC()
        raw = bytearray(ac.encode_on())
        raw[10] ^= 0xFF  # Corrupt a byte
        with pytest.raises(ValueError, match="Checksum"):
            FujitsuAC.from_bytes(bytes(raw))

    def test_decode_long_too_short(self) -> None:
        """Raise ValueError when a long message header claims full state but data is truncated."""
        ac = FujitsuAC()
        raw = ac.encode_on()
        truncated = raw[:10]  # Only 10 of 16 bytes
        with pytest.raises(ValueError, match="Long message too short"):
            FujitsuAC.from_bytes(truncated)


# =============================================================================
# Round-trip encoding/decoding
# =============================================================================


class TestRoundTrip:
    """Tests that encode → decode → re-encode produces identical bytes."""

    @pytest.mark.parametrize(
        "state",
        [
            FujitsuACState(power=True, mode=MODE_COOL, temperature=24.0, fan=FAN_AUTO, swing=SWING_OFF),
            FujitsuACState(power=True, mode=MODE_HEAT, temperature=28.0, fan=FAN_HIGH, swing=SWING_VERT),
            FujitsuACState(power=True, mode=MODE_DRY, temperature=22.0, fan=FAN_LOW, swing=SWING_HORIZ),
            FujitsuACState(power=True, mode=MODE_FAN, temperature=16.0, fan=FAN_QUIET, swing=SWING_BOTH),
            FujitsuACState(power=True, mode=MODE_AUTO, temperature=30.0, fan=FAN_MED, swing=SWING_OFF),
            FujitsuACState(power=True, mode=MODE_COOL, temperature=16.5, fan=FAN_AUTO, swing=SWING_OFF),
            FujitsuACState(power=True, mode=MODE_COOL, temperature=24.0, outside_quiet=True),
            FujitsuACState(power=True, mode=MODE_COOL, temperature=24.0, filter_active=True),
            FujitsuACState(power=True, mode=MODE_COOL, temperature=24.0, clean=True),
        ],
        ids=[
            "cool-24-auto-noswing",
            "heat-28-high-vert",
            "dry-22-low-horiz",
            "fan-16-quiet-both",
            "auto-30-med-noswing",
            "cool-16.5-half-step",
            "outside-quiet-on",
            "filter-on",
            "clean-on",
        ],
    )
    def test_round_trip(self, state: FujitsuACState) -> None:
        """Encode, decode, and re-encode — bytes must match."""
        ac = FujitsuAC(state)
        original = ac.encode_on()

        decoded = FujitsuAC.from_bytes(original)
        re_encoded = decoded.encode()

        assert re_encoded == original

    def test_round_trip_all_device_ids(self) -> None:
        """Round-trip works for all 4 device IDs."""
        for dev_id in range(4):
            state = FujitsuACState(device_id=dev_id)
            ac = FujitsuAC(state)
            original = ac.encode_on()
            decoded = FujitsuAC.from_bytes(original)
            assert decoded.state.device_id == dev_id
            assert decoded.encode() == original

    def test_round_trip_standard_protocol(self) -> None:
        """Round-trip works with the standard (0x30) protocol."""
        state = FujitsuACState(
            protocol=PROTOCOL_STANDARD,
            temperature=24.0,
            mode=MODE_COOL,
        )
        ac = FujitsuAC(state)
        original = ac.encode_on()
        decoded = FujitsuAC.from_bytes(original)
        assert decoded.state.protocol == PROTOCOL_STANDARD
        assert decoded.state.temperature == 24.0
        assert decoded.encode() == original


# =============================================================================
# Temperature property
# =============================================================================


class TestTemperatureProperty:
    """Tests for the temperature getter/setter on FujitsuAC."""

    def test_get_temperature(self) -> None:
        """Property returns the underlying state temperature."""
        ac = FujitsuAC(FujitsuACState(temperature=22.0))
        assert ac.temperature == 22.0

    def test_set_temperature_clamps_low(self) -> None:
        """Setting below MIN_TEMP clamps to MIN_TEMP."""
        ac = FujitsuAC()
        ac.temperature = 5.0
        assert ac.temperature == MIN_TEMP

    def test_set_temperature_clamps_high(self) -> None:
        """Setting above MAX_TEMP clamps to MAX_TEMP."""
        ac = FujitsuAC()
        ac.temperature = 50.0
        assert ac.temperature == MAX_TEMP


# =============================================================================
# Describe / pretty-print
# =============================================================================


class TestDescribe:
    """Tests for the describe and describe_bytes methods."""

    def test_describe_short_command(self) -> None:
        """Describe a short command."""
        ac = FujitsuAC()
        ac.command = CMD_TURN_OFF
        text = ac.describe()
        assert "Turn Off" in text

    def test_describe_long_command(self) -> None:
        """Describe a long state command."""
        ac = FujitsuAC(FujitsuACState(mode=MODE_COOL, temperature=24.0))
        ac.command = CMD_TURN_ON
        text = ac.describe()
        assert "Cool" in text
        assert "24.0" in text

    def test_bytes_to_hex(self) -> None:
        """bytes_to_hex produces space-separated hex."""
        result = FujitsuAC.bytes_to_hex(b"\x14\x63\x00")
        assert result == "14 63 00"

    def test_describe_bytes_short(self) -> None:
        """describe_bytes works on 7-byte messages."""
        ac = FujitsuAC()
        data = ac.encode_off()
        text = FujitsuAC.describe_bytes(data)
        assert "Header" in text
        assert "Inverse" in text

    def test_describe_bytes_long(self) -> None:
        """describe_bytes works on 16-byte messages."""
        ac = FujitsuAC()
        data = ac.encode_on()
        text = FujitsuAC.describe_bytes(data)
        assert "Checksum" in text
        assert "Protocol" in text


# =============================================================================
# Timer encoding
# =============================================================================


class TestTimerEncoding:
    """Tests for timer encoding in bytes 9, 11-13."""

    def test_no_timer_default(self) -> None:
        """Default state has no timer set (bytes 11-13 all zero)."""
        ac = FujitsuAC()
        data = ac.encode_on()
        assert data[11] == 0x00
        assert data[12] == 0x00
        assert data[13] == 0x00
        assert (data[9] >> 4) & 0x03 == TIMER_STOP

    def test_off_timer_30m(self) -> None:
        """Off timer 30 minutes matches known IRremoteESP8266 test vector."""
        state = FujitsuACState(
            power=True,
            mode=MODE_AUTO,
            temperature=26.0,
            fan=FAN_HIGH,
            swing=SWING_OFF,
            protocol=PROTOCOL_STANDARD,
            timer_type=TIMER_OFF,
            off_timer_minutes=30,
        )
        ac = FujitsuAC(state)
        data = ac.encode_on()
        # Timer type in byte 9 bits 5:4
        assert (data[9] >> 4) & 0x03 == TIMER_OFF
        # Decode timer bytes
        off_timer = (data[11] & 0xFF) | ((data[12] & 0x07) << 8)
        off_enable = bool(data[12] & 0x08)
        assert off_timer == 30
        assert off_enable is True

    def test_off_timer_11h(self) -> None:
        """Off timer 11 hours (660 minutes)."""
        state = FujitsuACState(
            power=True,
            timer_type=TIMER_OFF,
            off_timer_minutes=660,
        )
        ac = FujitsuAC(state)
        data = ac.encode_on()
        off_timer = (data[11] & 0xFF) | ((data[12] & 0x07) << 8)
        assert off_timer == 660
        assert bool(data[12] & 0x08) is True

    def test_on_timer_720m(self) -> None:
        """On timer 12 hours (720 minutes) — maximum value."""
        state = FujitsuACState(
            power=True,
            timer_type=TIMER_ON,
            on_timer_minutes=720,
        )
        ac = FujitsuAC(state)
        data = ac.encode_on()
        assert (data[9] >> 4) & 0x03 == TIMER_ON
        on_timer = ((data[12] >> 4) & 0x0F) | ((data[13] & 0x7F) << 4)
        on_enable = bool(data[13] & 0x80)
        assert on_timer == 720
        assert on_enable is True

    def test_on_timer_510m(self) -> None:
        """On timer 8h30m (510 minutes)."""
        state = FujitsuACState(
            power=True,
            timer_type=TIMER_ON,
            on_timer_minutes=510,
        )
        ac = FujitsuAC(state)
        data = ac.encode_on()
        on_timer = ((data[12] >> 4) & 0x0F) | ((data[13] & 0x7F) << 4)
        assert on_timer == 510
        assert bool(data[13] & 0x80) is True

    def test_sleep_timer_180m(self) -> None:
        """Sleep timer 3 hours (180 minutes)."""
        state = FujitsuACState(
            power=True,
            timer_type=TIMER_SLEEP,
            off_timer_minutes=180,
        )
        ac = FujitsuAC(state)
        data = ac.encode_on()
        assert (data[9] >> 4) & 0x03 == TIMER_SLEEP
        off_timer = (data[11] & 0xFF) | ((data[12] & 0x07) << 8)
        assert off_timer == 180
        assert bool(data[12] & 0x08) is True

    def test_timer_clamped_to_max(self) -> None:
        """Timer values above TIMER_MAX are clamped."""
        state = FujitsuACState(
            power=True,
            timer_type=TIMER_ON,
            on_timer_minutes=9999,
        )
        ac = FujitsuAC(state)
        data = ac.encode_on()
        on_timer = ((data[12] >> 4) & 0x0F) | ((data[13] & 0x7F) << 4)
        assert on_timer == TIMER_MAX

    def test_off_timer_enable_not_set_when_zero(self) -> None:
        """OffTimerEnable is not set when off_timer_minutes is 0."""
        state = FujitsuACState(
            power=True,
            timer_type=TIMER_OFF,
            off_timer_minutes=0,
        )
        ac = FujitsuAC(state)
        data = ac.encode_on()
        assert bool(data[12] & 0x08) is False

    def test_on_timer_enable_not_set_when_zero(self) -> None:
        """OnTimerEnable is not set when on_timer_minutes is 0."""
        state = FujitsuACState(
            power=True,
            timer_type=TIMER_ON,
            on_timer_minutes=0,
        )
        ac = FujitsuAC(state)
        data = ac.encode_on()
        assert bool(data[13] & 0x80) is False

    def test_timer_checksum_valid(self) -> None:
        """Checksum is valid when timer is set."""
        state = FujitsuACState(
            power=True,
            timer_type=TIMER_OFF,
            off_timer_minutes=60,
        )
        ac = FujitsuAC(state)
        data = ac.encode_on()
        assert (sum(data[7:16]) & 0xFF) == 0


# =============================================================================
# Timer decoding
# =============================================================================


class TestTimerDecoding:
    """Tests for timer decoding from raw bytes."""

    def test_decode_no_timer(self) -> None:
        """Default state has timer_type TIMER_STOP and zero minutes."""
        ac = FujitsuAC()
        data = ac.encode_on()
        decoded = FujitsuAC.from_bytes(data)
        assert decoded.state.timer_type == TIMER_STOP
        assert decoded.state.off_timer_minutes == 0
        assert decoded.state.on_timer_minutes == 0

    def test_decode_off_timer(self) -> None:
        """Decode an off timer message."""
        state = FujitsuACState(
            power=True,
            timer_type=TIMER_OFF,
            off_timer_minutes=120,
        )
        ac = FujitsuAC(state)
        data = ac.encode_on()
        decoded = FujitsuAC.from_bytes(data)
        assert decoded.state.timer_type == TIMER_OFF
        assert decoded.state.off_timer_minutes == 120
        assert decoded.state.on_timer_minutes == 0

    def test_decode_on_timer(self) -> None:
        """Decode an on timer message."""
        state = FujitsuACState(
            power=True,
            timer_type=TIMER_ON,
            on_timer_minutes=450,
        )
        ac = FujitsuAC(state)
        data = ac.encode_on()
        decoded = FujitsuAC.from_bytes(data)
        assert decoded.state.timer_type == TIMER_ON
        assert decoded.state.on_timer_minutes == 450
        assert decoded.state.off_timer_minutes == 0

    def test_decode_sleep_timer(self) -> None:
        """Decode a sleep timer message."""
        state = FujitsuACState(
            power=True,
            timer_type=TIMER_SLEEP,
            off_timer_minutes=90,
        )
        ac = FujitsuAC(state)
        data = ac.encode_on()
        decoded = FujitsuAC.from_bytes(data)
        assert decoded.state.timer_type == TIMER_SLEEP
        assert decoded.state.off_timer_minutes == 90


# =============================================================================
# Timer round-trip
# =============================================================================


class TestTimerRoundTrip:
    """Tests for encode → decode → re-encode round-trip with timers."""

    @pytest.mark.parametrize(
        "state",
        [
            FujitsuACState(
                power=True, timer_type=TIMER_OFF, off_timer_minutes=30,
            ),
            FujitsuACState(
                power=True, timer_type=TIMER_OFF, off_timer_minutes=660,
            ),
            FujitsuACState(
                power=True, timer_type=TIMER_ON, on_timer_minutes=720,
            ),
            FujitsuACState(
                power=True, timer_type=TIMER_ON, on_timer_minutes=510,
            ),
            FujitsuACState(
                power=True, timer_type=TIMER_SLEEP, off_timer_minutes=180,
            ),
            FujitsuACState(
                power=True, timer_type=TIMER_STOP,
            ),
        ],
        ids=[
            "off-30m",
            "off-11h",
            "on-12h",
            "on-8h30m",
            "sleep-3h",
            "no-timer",
        ],
    )
    def test_timer_round_trip(self, state: FujitsuACState) -> None:
        """Encode, decode, and re-encode — bytes must match."""
        ac = FujitsuAC(state)
        original = ac.encode_on()
        decoded = FujitsuAC.from_bytes(original)
        re_encoded = decoded.encode()
        assert re_encoded == original


# =============================================================================
# Timer in describe output
# =============================================================================


class TestTimerDescribe:
    """Tests for timer information in describe output."""

    def test_describe_includes_off_timer(self) -> None:
        """describe() mentions the off timer when active."""
        ac = FujitsuAC(FujitsuACState(
            power=True, timer_type=TIMER_OFF, off_timer_minutes=90,
        ))
        text = ac.describe()
        assert "Off Timer" in text
        assert "01:30" in text

    def test_describe_includes_on_timer(self) -> None:
        """describe() mentions the on timer when active."""
        ac = FujitsuAC(FujitsuACState(
            power=True, timer_type=TIMER_ON, on_timer_minutes=510,
        ))
        text = ac.describe()
        assert "On Timer" in text
        assert "08:30" in text

    def test_describe_bytes_shows_timer_values(self) -> None:
        """describe_bytes() shows decoded timer values."""
        ac = FujitsuAC(FujitsuACState(
            power=True, timer_type=TIMER_OFF, off_timer_minutes=60,
        ))
        data = ac.encode_on()
        text = FujitsuAC.describe_bytes(data)
        assert "OffTimer" in text
        assert "60 min" in text
