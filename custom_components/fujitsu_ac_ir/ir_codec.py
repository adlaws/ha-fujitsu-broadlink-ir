"""Fujitsu AC IR Protocol Encoder.

Encodes AC state into raw IR protocol bytes and converts to
Broadlink IR blaster format. Supports the AR-RWE3E / ARREW4E
protocol (byte 7 = 0x31).
"""

from __future__ import annotations

import base64
from dataclasses import dataclass

from .const import (
    BIT_MARK,
    BROADLINK_IR_TYPE,
    BROADLINK_TICK_US,
    CMD_LONG_STATE,
    CMD_TURN_OFF,
    FAN_AUTO,
    HEADER_BYTE0,
    HEADER_BYTE1,
    HEADER_BYTE3,
    HEADER_BYTE4,
    HEADER_MARK,
    HEADER_SPACE,
    MAX_TEMP,
    MIN_GAP,
    MIN_TEMP,
    MODE_COOL,
    ONE_SPACE,
    PROTOCOL_ARREW4E,
    STATE_LENGTH,
    STATE_LENGTH_SHORT,
    SWING_OFF,
    ZERO_SPACE,
)


@dataclass
class FujitsuACState:
    """Represent the full state of a Fujitsu AC unit.

    :param power: Whether the unit is on.
    :param mode: Operating mode (see ``MODE_*`` constants).
    :param temperature: Target temperature in °C.
    :param fan: Fan speed (see ``FAN_*`` constants).
    :param swing: Swing mode (see ``SWING_*`` constants).
    :param outside_quiet: Enable outside-unit quiet mode.
    :param device_id: Remote device ID (0–3).
    :param protocol: Protocol version byte.
    """

    power: bool = False
    mode: int = MODE_COOL
    temperature: float = 24.0
    fan: int = FAN_AUTO
    swing: int = SWING_OFF
    outside_quiet: bool = False
    device_id: int = 0
    protocol: int = PROTOCOL_ARREW4E


class FujitsuACCodec:
    """Encode/decode Fujitsu AC IR commands for Broadlink integration."""

    # =========================================================================
    # High-level: Build Broadlink base64 codes
    # =========================================================================

    @classmethod
    def build_power_on(cls, state: FujitsuACState) -> str:
        """Build a Broadlink base64 code to turn on with the given state.

        :param state: Desired AC state.
        :return: Base64-encoded Broadlink IR code.
        """
        ir_bytes = cls._encode_long(state, power_on=True)
        return cls._bytes_to_broadlink(ir_bytes)

    @classmethod
    def build_state_change(cls, state: FujitsuACState) -> str:
        """Build a Broadlink base64 code to change settings while on.

        :param state: Desired AC state.
        :return: Base64-encoded Broadlink IR code.
        """
        ir_bytes = cls._encode_long(state, power_on=False)
        return cls._bytes_to_broadlink(ir_bytes)

    @classmethod
    def build_power_off(cls) -> str:
        """Build a Broadlink base64 code to turn the unit off.

        :return: Base64-encoded Broadlink IR code.
        """
        ir_bytes = cls._encode_short(CMD_TURN_OFF)
        return cls._bytes_to_broadlink(ir_bytes)

    @classmethod
    def build_command(cls, state: FujitsuACState) -> str:
        """Build the appropriate Broadlink command for the current state.

        Send a power-off short code when *power* is ``False``, or a full
        state message when *power* is ``True``.

        :param state: Desired AC state.
        :return: Base64-encoded Broadlink IR code.
        """
        if not state.power:
            return cls.build_power_off()
        return cls.build_power_on(state)

    # =========================================================================
    # Protocol Encoding
    # =========================================================================

    @classmethod
    def _encode_short(cls, cmd: int, device_id: int = 0) -> bytes:
        """Build a 7-byte short command message.

        :param cmd: Command byte.
        :param device_id: Remote device ID (0–3).
        :return: Encoded 7-byte message.
        """
        data = bytearray(STATE_LENGTH_SHORT)
        data[0] = HEADER_BYTE0
        data[1] = HEADER_BYTE1
        data[2] = (device_id & 0x03) << 4
        data[3] = HEADER_BYTE3
        data[4] = HEADER_BYTE4
        data[5] = cmd
        data[6] = (~cmd) & 0xFF
        return bytes(data)

    @classmethod
    def _encode_long(cls, state: FujitsuACState, power_on: bool = True) -> bytes:
        """Build a 16-byte full state message.

        :param state: AC state to encode.
        :param power_on: Whether this is a power-on command.
        :return: Encoded 16-byte message.
        """
        data = bytearray(STATE_LENGTH)

        # Fixed header (bytes 0-4)
        data[0] = HEADER_BYTE0
        data[1] = HEADER_BYTE1
        data[2] = (state.device_id & 0x03) << 4
        data[3] = HEADER_BYTE3
        data[4] = HEADER_BYTE4

        # Byte 5: Long command indicator
        data[5] = CMD_LONG_STATE  # 0xFE

        # Byte 6: RestLength
        data[6] = STATE_LENGTH - 7  # = 9

        # Byte 7: Protocol version
        data[7] = state.protocol

        # Byte 8: Power (bit 0), Temperature (bits 7:2)
        temp = max(MIN_TEMP, min(MAX_TEMP, state.temperature))
        if state.protocol == PROTOCOL_ARREW4E:
            temp_encoded = int((temp - 8.0) * 2) & 0x3F
        else:
            temp_encoded = int((temp - MIN_TEMP) * 4) & 0x3F
        power_bit = 1 if (power_on or state.power) else 0
        data[8] = (temp_encoded << 2) | power_bit

        # Byte 9: Mode (bits 2:0)
        data[9] = state.mode & 0x07

        # Byte 10: Fan (bits 2:0), Swing (bits 5:4)
        data[10] = (state.fan & 0x07) | ((state.swing & 0x03) << 4)

        # Bytes 11-13: Timers (disabled)
        data[11] = 0x00
        data[12] = 0x00
        data[13] = 0x00

        # Byte 14: Unknown=1 (bit 5), model-specific bit 0
        data[14] = (1 << 5)  # Unknown bit always set
        if state.protocol == PROTOCOL_ARREW4E:
            data[14] |= 0x01  # Bit 0 always set on AR-RWE3E / ARREW4E
        if state.outside_quiet:
            data[14] |= (1 << 7)

        # Byte 15: Checksum (sum of bytes 7-15 == 0 mod 256)
        checksum = sum(data[7:15]) & 0xFF
        data[15] = (256 - checksum) & 0xFF

        return bytes(data)

    # =========================================================================
    # Protocol Decoding
    # =========================================================================

    @classmethod
    def decode_bytes(cls, data: bytes) -> FujitsuACState:
        """Decode raw IR protocol bytes into an AC state.

        :param data: Raw protocol bytes (7 or 16 bytes).
        :return: Decoded ``FujitsuACState``.
        :raises ValueError: If the data is too short or has an invalid header.
        """
        if len(data) < STATE_LENGTH_SHORT:
            raise ValueError(
                f"Data too short: {len(data)} bytes "
                f"(minimum {STATE_LENGTH_SHORT})"
            )

        # Validate fixed header
        if data[0] != HEADER_BYTE0 or data[1] != HEADER_BYTE1:
            raise ValueError(
                f"Invalid header: 0x{data[0]:02X} 0x{data[1]:02X} "
                f"(expected 0x{HEADER_BYTE0:02X} 0x{HEADER_BYTE1:02X})"
            )

        state = FujitsuACState()
        cmd_byte = data[5]

        if cmd_byte == CMD_LONG_STATE and len(data) >= STATE_LENGTH:
            # Verify checksum: sum of bytes 7-15 must be 0 mod 256
            if (sum(data[STATE_LENGTH_SHORT:STATE_LENGTH]) & 0xFF) != 0:
                raise ValueError("Checksum mismatch")

            state.protocol = data[7]
            state.power = bool(data[8] & 0x01)
            temp_raw = (data[8] >> 2) & 0x3F
            if state.protocol == PROTOCOL_ARREW4E:
                state.temperature = (temp_raw / 2.0) + 8.0
            else:
                state.temperature = (temp_raw / 4.0) + MIN_TEMP
            state.mode = data[9] & 0x07
            state.fan = data[10] & 0x07
            state.swing = (data[10] >> 4) & 0x03
            state.outside_quiet = bool(data[14] & 0x80)
        elif cmd_byte == CMD_TURN_OFF:
            state.power = False

        return state

    # =========================================================================
    # Broadlink IR Format Conversion
    # =========================================================================

    @classmethod
    def _bytes_to_broadlink(cls, data: bytes) -> str:
        """Convert protocol bytes to Broadlink base64 via IR timings.

        :param data: Fujitsu AC protocol bytes.
        :return: Base64-encoded Broadlink IR code.
        """
        timings = cls._bytes_to_timings(data)
        return cls._timings_to_broadlink(timings)

    @staticmethod
    def _bytes_to_timings(data: bytes) -> list[int]:
        """Encode protocol bytes into raw IR timing values.

        :param data: Fujitsu AC protocol bytes.
        :return: Alternating mark/space durations in microseconds.
        """
        timings = [HEADER_MARK, HEADER_SPACE]

        for byte_val in data:
            for bit_idx in range(8):
                bit = (byte_val >> bit_idx) & 1
                timings.append(BIT_MARK)
                timings.append(ONE_SPACE if bit else ZERO_SPACE)

        timings.append(BIT_MARK)
        timings.append(MIN_GAP)
        return timings

    @staticmethod
    def _timings_to_broadlink(timings_us: list[int], repeat: int = 0) -> str:
        """Encode raw timing values into Broadlink base64 format.

        :param timings_us: Alternating mark/space durations in microseconds.
        :param repeat: Number of times to repeat the signal.
        :return: Base64-encoded Broadlink IR code.
        """
        timing_bytes = bytearray()
        for us in timings_us:
            ticks = round(us / BROADLINK_TICK_US)
            if ticks > 255:
                timing_bytes.append(0x00)
                timing_bytes.append((ticks >> 8) & 0xFF)
                timing_bytes.append(ticks & 0xFF)
            else:
                timing_bytes.append(max(1, ticks))

        data_len = len(timing_bytes)
        packet = bytearray()
        packet.append(BROADLINK_IR_TYPE)
        packet.append(repeat & 0xFF)
        packet.append(data_len & 0xFF)
        packet.append((data_len >> 8) & 0xFF)
        packet.extend(timing_bytes)
        packet.append(0x0D)
        packet.append(0x05)

        return base64.b64encode(bytes(packet)).decode("ascii")

    # Timing thresholds for distinguishing IR signal components (µs)
    _HEADER_MARK_MIN = 2500
    _GAP_MIN = 5000
    _ONE_SPACE_MIN = 800

    @classmethod
    def broadlink_to_bytes(cls, code: str) -> bytes:
        """Decode a Broadlink base64 code to protocol bytes.

        :param code: Base64-encoded Broadlink IR code.
        :return: Decoded protocol bytes.
        :raises ValueError: If the code is invalid.
        """
        raw = base64.b64decode(code)
        if len(raw) < 4 or raw[0] != BROADLINK_IR_TYPE:
            raise ValueError("Invalid Broadlink IR code")

        data_len = raw[2] | (raw[3] << 8)
        timings: list[int] = []
        i = 4
        end = min(4 + data_len, len(raw))
        while i < end:
            if raw[i] == 0x00:
                if i + 2 < end:
                    ticks = (raw[i + 1] << 8) | raw[i + 2]
                    i += 3
                else:
                    break  # Incomplete extended-length value
            else:
                ticks = raw[i]
                i += 1
            timings.append(round(ticks * BROADLINK_TICK_US))

        # Extract bits after header
        bits: list[int] = []
        idx = 2
        while idx + 1 < len(timings):
            mark, space = timings[idx], timings[idx + 1]
            if mark > cls._HEADER_MARK_MIN or space > cls._GAP_MIN:
                break
            bits.append(1 if space > cls._ONE_SPACE_MIN else 0)
            idx += 2

        # Assemble LSB-first bytes
        result = bytearray()
        for byte_start in range(0, len(bits), 8):
            byte_bits = bits[byte_start : byte_start + 8]
            if len(byte_bits) < 8:
                break
            val = sum(b << i for i, b in enumerate(byte_bits))
            result.append(val)

        return bytes(result)
