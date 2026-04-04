"""Tests using real recorded Broadlink IR codes.

These tests decode every code from the recorded JSON file, verify
round-trip encoding, and check that specific known codes decode to
the expected AC state.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from fujitsu_ir.broadlink import BroadlinkIR
from fujitsu_ir.const import (
    CMD_TURN_OFF,
    CMD_TURN_ON,
    FAN_AUTO,
    FAN_HIGH,
    FAN_LOW,
    FAN_MED,
    FAN_QUIET,
    MODE_AUTO,
    MODE_COOL,
    MODE_DRY,
    MODE_FAN,
    MODE_HEAT,
    STATE_LENGTH,
    SWING_BOTH,
    SWING_HORIZ,
    SWING_OFF,
    SWING_VERT,
)
from fujitsu_ir.protocol import FujitsuAC, SHORT_COMMANDS

# ---------------------------------------------------------------------------
# Load the recorded codes once for the whole module
# ---------------------------------------------------------------------------

_JSON_PATH = Path(__file__).resolve().parent.parent / "resources" / "fujitsu-ir-codes-broadlink.json"


def _load_codes() -> dict[str, str]:
    """Load all recorded IR codes from the JSON resource file.

    :return: Mapping of code name to base64-encoded Broadlink IR code.
    """
    data = json.loads(_JSON_PATH.read_text(encoding="utf-8"))
    for _device_name, device_codes in data.get("data", {}).items():
        return device_codes
    return data


CODES = _load_codes()


# =============================================================================
# Every recorded code must decode without error
# =============================================================================


class TestAllCodesDecodable:
    """Verify that every recorded code can be decoded."""

    @pytest.mark.parametrize("name", list(CODES.keys()))
    def test_decode_succeeds(self, name: str) -> None:
        """Each code decodes to valid protocol bytes and a FujitsuAC state."""
        code = CODES[name]
        ir_bytes = BroadlinkIR.broadlink_to_bytes(code)
        ac = FujitsuAC.from_bytes(ir_bytes)
        assert ac is not None


# =============================================================================
# Round-trip: recorded code → decode → re-encode → compare
# =============================================================================


class TestRecordedRoundTrip:
    """Verify that decoding and re-encoding preserves all state fields.

    The recorded codes include the remote's clock timestamp in bytes 11–13
    which varies between captures and is not preserved during re-encoding
    (the library zeroes timer bytes).  We therefore compare decoded state
    fields rather than raw bytes, and verify the re-encoded checksum is valid.
    """

    @pytest.mark.parametrize("name", list(CODES.keys()))
    def test_round_trip_state(self, name: str) -> None:
        """Decode, re-encode, decode again — state fields must match."""
        code = CODES[name]
        ir_bytes = BroadlinkIR.broadlink_to_bytes(code)
        ac = FujitsuAC.from_bytes(ir_bytes)

        re_encoded = ac.encode()
        ac2 = FujitsuAC.from_bytes(re_encoded)

        # Short commands should byte-match exactly
        if ac.command in SHORT_COMMANDS or ac.command == CMD_TURN_OFF:
            assert re_encoded == ir_bytes
            return

        # Long commands: all state fields must match
        assert ac2.state.power == ac.state.power
        assert ac2.state.mode == ac.state.mode
        assert ac2.state.temperature == ac.state.temperature
        assert ac2.state.fan == ac.state.fan
        assert ac2.state.swing == ac.state.swing
        assert ac2.state.outside_quiet == ac.state.outside_quiet
        assert ac2.state.filter_active == ac.state.filter_active
        assert ac2.state.clean == ac.state.clean
        assert ac2.state.device_id == ac.state.device_id
        assert ac2.state.protocol == ac.state.protocol

    @pytest.mark.parametrize("name", list(CODES.keys()))
    def test_re_encoded_checksum_valid(self, name: str) -> None:
        """Re-encoded long messages have a valid checksum."""
        code = CODES[name]
        ir_bytes = BroadlinkIR.broadlink_to_bytes(code)
        ac = FujitsuAC.from_bytes(ir_bytes)
        re_encoded = ac.encode()

        if len(re_encoded) == STATE_LENGTH:
            assert FujitsuAC.verify_checksum(re_encoded)


# =============================================================================
# Spot-check specific known codes
# =============================================================================


class TestKnownCodes:
    """Verify that specific recorded codes decode to expected values."""

    @pytest.mark.skipif("off" not in CODES, reason="'off' code not in JSON")
    def test_off_command(self) -> None:
        """The 'off' code decodes as a power-off command."""
        ir_bytes = BroadlinkIR.broadlink_to_bytes(CODES["off"])
        ac = FujitsuAC.from_bytes(ir_bytes)
        assert ac.command == CMD_TURN_OFF
        assert ac.state.power is False

    @pytest.mark.skipif("on" not in CODES, reason="'on' code not in JSON")
    def test_on_command(self) -> None:
        """The 'on' code decodes as a power-on command with power=True."""
        ir_bytes = BroadlinkIR.broadlink_to_bytes(CODES["on"])
        ac = FujitsuAC.from_bytes(ir_bytes)
        assert ac.state.power is True

    @pytest.mark.skipif("mode_cool" not in CODES, reason="'mode_cool' code not in JSON")
    def test_mode_cool(self) -> None:
        """The 'mode_cool' code decodes to MODE_COOL."""
        ir_bytes = BroadlinkIR.broadlink_to_bytes(CODES["mode_cool"])
        ac = FujitsuAC.from_bytes(ir_bytes)
        assert ac.state.mode == MODE_COOL

    @pytest.mark.skipif("mode_heat" not in CODES, reason="'mode_heat' code not in JSON")
    def test_mode_heat(self) -> None:
        """The 'mode_heat' code decodes to MODE_HEAT."""
        ir_bytes = BroadlinkIR.broadlink_to_bytes(CODES["mode_heat"])
        ac = FujitsuAC.from_bytes(ir_bytes)
        assert ac.state.mode == MODE_HEAT

    @pytest.mark.skipif("mode_dry" not in CODES, reason="'mode_dry' code not in JSON")
    def test_mode_dry(self) -> None:
        """The 'mode_dry' code decodes to MODE_DRY."""
        ir_bytes = BroadlinkIR.broadlink_to_bytes(CODES["mode_dry"])
        ac = FujitsuAC.from_bytes(ir_bytes)
        assert ac.state.mode == MODE_DRY

    @pytest.mark.skipif("mode_fan" not in CODES, reason="'mode_fan' code not in JSON")
    def test_mode_fan(self) -> None:
        """The 'mode_fan' code decodes to MODE_FAN."""
        ir_bytes = BroadlinkIR.broadlink_to_bytes(CODES["mode_fan"])
        ac = FujitsuAC.from_bytes(ir_bytes)
        assert ac.state.mode == MODE_FAN

    @pytest.mark.skipif("mode_auto" not in CODES, reason="'mode_auto' code not in JSON")
    def test_mode_auto(self) -> None:
        """The 'mode_auto' code decodes to MODE_AUTO."""
        ir_bytes = BroadlinkIR.broadlink_to_bytes(CODES["mode_auto"])
        ac = FujitsuAC.from_bytes(ir_bytes)
        assert ac.state.mode == MODE_AUTO
