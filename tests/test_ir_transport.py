"""Tests for the Home Assistant integration IR transport layer.

Tests the self-contained transport utilities in
``custom_components/fujitsu_ac_ir/ir_transport.py`` — specifically the
Broadlink, ESPHome, SwitchBot, and Aqara format conversion helpers
and the transport factory.

The async ``async_send_timings`` method is not tested here because it
requires a running Home Assistant instance.
"""

from __future__ import annotations

import base64
import json
import sys
import types
from pathlib import Path

import pytest

# ---------------------------------------------------------------------------
# Stub the homeassistant package so the integration modules can import
# without Home Assistant installed.
# ---------------------------------------------------------------------------
_CC_ROOT = Path(__file__).resolve().parent.parent / "custom_components"
if str(_CC_ROOT) not in sys.path:
    sys.path.insert(0, str(_CC_ROOT))

_pkg = types.ModuleType("fujitsu_ac_ir")
_pkg.__path__ = [str(_CC_ROOT / "fujitsu_ac_ir")]
_pkg.__package__ = "fujitsu_ac_ir"
sys.modules.setdefault("fujitsu_ac_ir", _pkg)

# Stub homeassistant modules used by ir_transport
for _mod_name in (
    "homeassistant",
    "homeassistant.core",
):
    sys.modules.setdefault(_mod_name, types.ModuleType(_mod_name))

# Provide a stub HomeAssistant class so ``IRTransport.__init__`` type checks
# don't fail at import time.
_ha_core = sys.modules["homeassistant.core"]
if not hasattr(_ha_core, "HomeAssistant"):

    class _StubHomeAssistant:  # noqa: D101
        pass

    _ha_core.HomeAssistant = _StubHomeAssistant  # type: ignore[attr-defined]

import fujitsu_ac_ir.const as _const_mod  # noqa: E402
import fujitsu_ac_ir.ir_transport as _transport_mod  # noqa: E402

from fujitsu_ac_ir.const import (
    BIT_MARK,
    BROADLINK_IR_TYPE,
    BROADLINK_TICK_US,
    HEADER_MARK,
    HEADER_SPACE,
    MIN_GAP,
    ONE_SPACE,
    ZERO_SPACE,
)
from fujitsu_ac_ir.ir_transport import (
    ENTITY_TRANSPORTS,
    TRANSPORT_AQARA,
    TRANSPORT_BROADLINK,
    TRANSPORT_ESPHOME,
    TRANSPORT_REGISTRY,
    TRANSPORT_SWITCHBOT,
    AqaraTransport,
    BroadlinkTransport,
    ESPHomeTransport,
    IRTransport,
    SwitchBotTransport,
    create_transport,
)


# =============================================================================
# Transport registry
# =============================================================================


class TestTransportRegistry:
    """Tests for the transport registry and factory function."""

    def test_broadlink_in_registry(self) -> None:
        """Registry contains the Broadlink transport."""
        assert TRANSPORT_BROADLINK in TRANSPORT_REGISTRY
        assert TRANSPORT_REGISTRY[TRANSPORT_BROADLINK] is BroadlinkTransport

    def test_create_transport_broadlink(self) -> None:
        """create_transport returns a BroadlinkTransport for 'broadlink'."""
        transport = create_transport(TRANSPORT_BROADLINK, None, "remote.test")  # type: ignore[arg-type]
        assert isinstance(transport, BroadlinkTransport)
        assert transport.entity_id == "remote.test"

    def test_create_transport_unknown_raises(self) -> None:
        """create_transport raises ValueError for unknown transport types."""
        with pytest.raises(ValueError, match="Unknown IR transport type"):
            create_transport("nonexistent", None, "remote.test")  # type: ignore[arg-type]

    def test_create_transport_error_message_lists_valid(self) -> None:
        """The ValueError message lists all registered transport types."""
        with pytest.raises(ValueError, match="broadlink"):
            create_transport("bad", None, "remote.test")  # type: ignore[arg-type]


# =============================================================================
# BroadlinkTransport.timings_to_broadlink
# =============================================================================


class TestTimingsToBroadlink:
    """Tests for BroadlinkTransport.timings_to_broadlink."""

    def test_returns_base64_string(self) -> None:
        """Output is a valid base64 string."""
        timings = [HEADER_MARK, HEADER_SPACE, BIT_MARK, ONE_SPACE]
        result = BroadlinkTransport.timings_to_broadlink(timings)
        # Should not raise
        raw = base64.b64decode(result)
        assert raw[0] == BROADLINK_IR_TYPE

    def test_packet_structure(self) -> None:
        """Encoded packet has correct header and trailer."""
        timings = [HEADER_MARK, HEADER_SPACE]
        result = BroadlinkTransport.timings_to_broadlink(timings)
        raw = base64.b64decode(result)
        # Byte 0: IR type marker
        assert raw[0] == BROADLINK_IR_TYPE
        # Byte 1: repeat count (default 0)
        assert raw[1] == 0x00
        # Last two bytes: trailer
        assert raw[-2] == 0x0D
        assert raw[-1] == 0x05

    def test_repeat_count(self) -> None:
        """Repeat count is encoded in byte 1."""
        timings = [HEADER_MARK, HEADER_SPACE]
        result = BroadlinkTransport.timings_to_broadlink(timings, repeat=3)
        raw = base64.b64decode(result)
        assert raw[1] == 0x03

    def test_extended_length_for_large_values(self) -> None:
        """Values > 255 ticks use the 3-byte extended encoding (0x00 prefix)."""
        # 10000 µs ÷ ~30.45 µs/tick ≈ 328 ticks > 255
        timings = [10000]
        result = BroadlinkTransport.timings_to_broadlink(timings)
        raw = base64.b64decode(result)
        # First timing byte (index 4) should be 0x00 (extended marker)
        assert raw[4] == 0x00

    def test_small_values_single_byte(self) -> None:
        """Values ≤ 255 ticks use single-byte encoding."""
        # 390 µs ÷ ~30.45 µs/tick ≈ 13 ticks — fits in one byte
        timings = [ZERO_SPACE]
        result = BroadlinkTransport.timings_to_broadlink(timings)
        raw = base64.b64decode(result)
        # Data length is just 1 byte (no extended marker)
        data_len = raw[2] | (raw[3] << 8)
        assert data_len == 1

    def test_minimum_tick_value(self) -> None:
        """Very small timing values are clamped to at least 1 tick."""
        timings = [1]  # ~0.03 ticks rounds to 0, clamped to 1
        result = BroadlinkTransport.timings_to_broadlink(timings)
        raw = base64.b64decode(result)
        assert raw[4] >= 1


# =============================================================================
# BroadlinkTransport.broadlink_to_timings
# =============================================================================


class TestBroadlinkToTimings:
    """Tests for BroadlinkTransport.broadlink_to_timings."""

    def test_rejects_invalid_type_marker(self) -> None:
        """Raise ValueError when byte 0 is not the IR marker."""
        bad = base64.b64encode(b"\xFF\x00\x01\x00\x05").decode()
        with pytest.raises(ValueError, match="Invalid"):
            BroadlinkTransport.broadlink_to_timings(bad)

    def test_rejects_short_data(self) -> None:
        """Raise ValueError when payload is too short."""
        short = base64.b64encode(b"\x26\x00").decode()
        with pytest.raises(ValueError, match="Invalid"):
            BroadlinkTransport.broadlink_to_timings(short)

    def test_round_trip_simple(self) -> None:
        """Encode timings to Broadlink, decode back — values match closely."""
        original = [HEADER_MARK, HEADER_SPACE, BIT_MARK, ONE_SPACE, BIT_MARK, MIN_GAP]
        encoded = BroadlinkTransport.timings_to_broadlink(original)
        decoded = BroadlinkTransport.broadlink_to_timings(encoded)
        assert len(decoded) == len(original)
        for orig, dec in zip(original, decoded):
            assert abs(orig - dec) < 35, f"Timing mismatch: {orig} vs {dec}"

    def test_round_trip_extended_values(self) -> None:
        """Extended-length values survive the round-trip."""
        original = [10000, 5000, 300]
        encoded = BroadlinkTransport.timings_to_broadlink(original)
        decoded = BroadlinkTransport.broadlink_to_timings(encoded)
        assert len(decoded) == len(original)
        for orig, dec in zip(original, decoded):
            assert abs(orig - dec) < 35


# =============================================================================
# IRTransport base class
# =============================================================================


class TestIRTransportBase:
    """Tests for the abstract IRTransport base class."""

    def test_cannot_instantiate_directly(self) -> None:
        """IRTransport is abstract and cannot be instantiated."""
        with pytest.raises(TypeError):
            IRTransport(None, "remote.test")  # type: ignore[abstract,arg-type]

    def test_entity_id_property(self) -> None:
        """The entity_id property returns the configured entity."""
        transport = create_transport(TRANSPORT_BROADLINK, None, "remote.my_blaster")  # type: ignore[arg-type]
        assert transport.entity_id == "remote.my_blaster"

    def test_entity_id_property_esphome(self) -> None:
        """entity_id returns the device name for ESPHome transports."""
        transport = create_transport(TRANSPORT_ESPHOME, None, "ir_blaster")  # type: ignore[arg-type]
        assert transport.entity_id == "ir_blaster"


# =============================================================================
# Transport registry — new backends
# =============================================================================


class TestTransportRegistryNewBackends:
    """Tests that all new backends are registered and discoverable."""

    def test_esphome_in_registry(self) -> None:
        """Registry contains the ESPHome transport."""
        assert TRANSPORT_ESPHOME in TRANSPORT_REGISTRY
        assert TRANSPORT_REGISTRY[TRANSPORT_ESPHOME] is ESPHomeTransport

    def test_switchbot_in_registry(self) -> None:
        """Registry contains the SwitchBot transport."""
        assert TRANSPORT_SWITCHBOT in TRANSPORT_REGISTRY
        assert TRANSPORT_REGISTRY[TRANSPORT_SWITCHBOT] is SwitchBotTransport

    def test_aqara_in_registry(self) -> None:
        """Registry contains the Aqara transport."""
        assert TRANSPORT_AQARA in TRANSPORT_REGISTRY
        assert TRANSPORT_REGISTRY[TRANSPORT_AQARA] is AqaraTransport

    def test_create_transport_esphome(self) -> None:
        """create_transport returns an ESPHomeTransport for 'esphome'."""
        transport = create_transport(TRANSPORT_ESPHOME, None, "ir_blaster")  # type: ignore[arg-type]
        assert isinstance(transport, ESPHomeTransport)
        assert transport.entity_id == "ir_blaster"

    def test_create_transport_switchbot(self) -> None:
        """create_transport returns a SwitchBotTransport for 'switchbot'."""
        transport = create_transport(TRANSPORT_SWITCHBOT, None, "remote.sb_hub")  # type: ignore[arg-type]
        assert isinstance(transport, SwitchBotTransport)
        assert transport.entity_id == "remote.sb_hub"

    def test_create_transport_aqara(self) -> None:
        """create_transport returns an AqaraTransport for 'aqara'."""
        transport = create_transport(TRANSPORT_AQARA, None, "remote.aqara_hub")  # type: ignore[arg-type]
        assert isinstance(transport, AqaraTransport)
        assert transport.entity_id == "remote.aqara_hub"

    def test_registry_has_four_transports(self) -> None:
        """All four transports are registered."""
        expected = {TRANSPORT_BROADLINK, TRANSPORT_ESPHOME, TRANSPORT_SWITCHBOT, TRANSPORT_AQARA}
        assert set(TRANSPORT_REGISTRY.keys()) == expected


# =============================================================================
# ENTITY_TRANSPORTS frozenset
# =============================================================================


class TestEntityTransports:
    """Tests for the ENTITY_TRANSPORTS frozenset."""

    def test_broadlink_is_entity_transport(self) -> None:
        """Broadlink uses an entity selector."""
        assert TRANSPORT_BROADLINK in ENTITY_TRANSPORTS

    def test_switchbot_is_entity_transport(self) -> None:
        """SwitchBot uses an entity selector."""
        assert TRANSPORT_SWITCHBOT in ENTITY_TRANSPORTS

    def test_aqara_is_entity_transport(self) -> None:
        """Aqara uses an entity selector."""
        assert TRANSPORT_AQARA in ENTITY_TRANSPORTS

    def test_esphome_is_not_entity_transport(self) -> None:
        """ESPHome uses a device name, not an entity."""
        assert TRANSPORT_ESPHOME not in ENTITY_TRANSPORTS

    def test_is_frozenset(self) -> None:
        """ENTITY_TRANSPORTS is immutable."""
        assert isinstance(ENTITY_TRANSPORTS, frozenset)


# =============================================================================
# ESPHomeTransport.timings_to_signed
# =============================================================================


class TestESPHomeTimingsToSigned:
    """Tests for ESPHomeTransport.timings_to_signed."""

    def test_simple_pair(self) -> None:
        """A mark/space pair produces [+mark, -space]."""
        assert ESPHomeTransport.timings_to_signed([3324, 1574]) == [3324, -1574]

    def test_marks_positive_spaces_negative(self) -> None:
        """Even indices stay positive, odd indices are negated."""
        timings = [3324, 1574, 448, 1182, 448, 390, 448, 390]
        signed = ESPHomeTransport.timings_to_signed(timings)
        for i, val in enumerate(signed):
            if i % 2 == 0:
                assert val > 0, f"Mark at index {i} should be positive"
            else:
                assert val < 0, f"Space at index {i} should be negative"

    def test_absolute_values_match(self) -> None:
        """Absolute values of the signed output match the input."""
        timings = [100, 200, 300, 400]
        signed = ESPHomeTransport.timings_to_signed(timings)
        assert [abs(v) for v in signed] == timings

    def test_empty_input(self) -> None:
        """Empty timings produce an empty list."""
        assert ESPHomeTransport.timings_to_signed([]) == []

    def test_single_mark(self) -> None:
        """Single element (trailing mark) stays positive."""
        assert ESPHomeTransport.timings_to_signed([500]) == [500]

    def test_zero_values(self) -> None:
        """Zero values are preserved (0 == -0)."""
        assert ESPHomeTransport.timings_to_signed([0, 0]) == [0, 0]

    def test_service_name_attribute(self) -> None:
        """ESPHomeTransport has the expected SERVICE_NAME."""
        assert ESPHomeTransport.SERVICE_NAME == "send_raw_ir"


# =============================================================================
# SwitchBotTransport.timings_to_command
# =============================================================================


class TestSwitchBotTimingsToCommand:
    """Tests for SwitchBotTransport.timings_to_command."""

    def test_returns_json_string(self) -> None:
        """Output is valid JSON."""
        timings = [3324, 1574, 448, 1182]
        result = SwitchBotTransport.timings_to_command(timings)
        parsed = json.loads(result)
        assert isinstance(parsed, list)

    def test_signed_values(self) -> None:
        """Marks are positive, spaces are negative in the JSON array."""
        timings = [3324, 1574, 448, 1182]
        parsed = json.loads(SwitchBotTransport.timings_to_command(timings))
        assert parsed == [3324, -1574, 448, -1182]

    def test_compact_json(self) -> None:
        """JSON uses compact separators (no extra spaces)."""
        timings = [100, 200]
        result = SwitchBotTransport.timings_to_command(timings)
        assert " " not in result
        assert result == "[100,-200]"

    def test_empty_input(self) -> None:
        """Empty timings produce an empty JSON array."""
        assert SwitchBotTransport.timings_to_command([]) == "[]"

    def test_single_element(self) -> None:
        """Single timing value produces single-element array."""
        result = SwitchBotTransport.timings_to_command([500])
        assert json.loads(result) == [500]


# =============================================================================
# AqaraTransport.timings_to_command
# =============================================================================


class TestAqaraTimingsToCommand:
    """Tests for AqaraTransport.timings_to_command."""

    def test_returns_json_string(self) -> None:
        """Output is valid JSON."""
        timings = [3324, 1574, 448, 1182]
        result = AqaraTransport.timings_to_command(timings)
        parsed = json.loads(result)
        assert isinstance(parsed, list)

    def test_signed_values(self) -> None:
        """Marks are positive, spaces are negative in the JSON array."""
        timings = [3324, 1574, 448, 1182]
        parsed = json.loads(AqaraTransport.timings_to_command(timings))
        assert parsed == [3324, -1574, 448, -1182]

    def test_compact_json(self) -> None:
        """JSON uses compact separators."""
        timings = [100, 200]
        result = AqaraTransport.timings_to_command(timings)
        assert result == "[100,-200]"

    def test_empty_input(self) -> None:
        """Empty timings produce an empty JSON array."""
        assert AqaraTransport.timings_to_command([]) == "[]"

    def test_matches_switchbot_format(self) -> None:
        """Aqara and SwitchBot use the same encoding format."""
        timings = [3324, 1574, 448, 1182, 448, 390]
        assert AqaraTransport.timings_to_command(timings) == \
            SwitchBotTransport.timings_to_command(timings)


# =============================================================================
# Cross-transport consistency
# =============================================================================


class TestCrossTransportConsistency:
    """Verify that all transports convert the same raw timings."""

    SAMPLE_TIMINGS = [3324, 1574, 448, 1182, 448, 390, 448, 390, 448, 10000]

    def test_esphome_switchbot_same_signed_values(self) -> None:
        """ESPHome signed output matches SwitchBot/Aqara parsed JSON values."""
        signed_esphome = ESPHomeTransport.timings_to_signed(self.SAMPLE_TIMINGS)
        signed_switchbot = json.loads(
            SwitchBotTransport.timings_to_command(self.SAMPLE_TIMINGS)
        )
        assert signed_esphome == signed_switchbot

    def test_broadlink_round_trip_preserves_count(self) -> None:
        """Broadlink encoding preserves the number of timing elements."""
        encoded = BroadlinkTransport.timings_to_broadlink(self.SAMPLE_TIMINGS)
        decoded = BroadlinkTransport.broadlink_to_timings(encoded)
        assert len(decoded) == len(self.SAMPLE_TIMINGS)
