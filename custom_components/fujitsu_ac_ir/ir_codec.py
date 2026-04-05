"""Fujitsu AC IR Protocol Encoder.

Encodes AC state into raw IR protocol bytes and converts to raw IR
timing arrays.  Transport-specific encoding (Broadlink base64, ESPHome
raw, etc.) is handled by :mod:`ir_transport`.

Supports the AR-RWE3E / ARREW4E protocol (byte 7 = 0x31).
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
    TIMER_MAX,
    TIMER_OFF,
    TIMER_ON,
    TIMER_SLEEP,
    TIMER_STOP,
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
    :param timer_type: Timer mode (``TIMER_STOP``, ``TIMER_SLEEP``,
        ``TIMER_OFF``, ``TIMER_ON``).  Only one timer can be active.
    :param off_timer_minutes: Duration in minutes for the off or sleep timer
        (0–720).  Also used when ``timer_type`` is ``TIMER_SLEEP``.
    :param on_timer_minutes: Duration in minutes for the on timer (0–720).
    """

    power: bool = False
    mode: int = MODE_COOL
    temperature: float = 24.0
    fan: int = FAN_AUTO
    swing: int = SWING_OFF
    outside_quiet: bool = False
    device_id: int = 0
    protocol: int = PROTOCOL_ARREW4E
    timer_type: int = TIMER_STOP
    off_timer_minutes: int = 0
    on_timer_minutes: int = 0


class FujitsuACCodec:
    """Encode/decode Fujitsu AC IR commands.

    Protocol layer only — converts between :class:`FujitsuACState` and
    raw IR protocol bytes or timing arrays.  Transport-specific
    formatting (Broadlink base64, ESPHome raw, etc.) is handled by
    :mod:`ir_transport`.
    """

    # =========================================================================
    # High-level: Build protocol bytes
    # =========================================================================

    @classmethod
    def build_power_on(cls, state: FujitsuACState) -> bytes:
        """Build protocol bytes to turn on with the given state.

        :param state: Desired AC state.
        :return: Encoded protocol bytes (16 bytes).
        """
        return cls._encode_long(state, power_on=True)

    @classmethod
    def build_state_change(cls, state: FujitsuACState) -> bytes:
        """Build protocol bytes to change settings while on.

        :param state: Desired AC state.
        :return: Encoded protocol bytes (16 bytes).
        """
        return cls._encode_long(state, power_on=False)

    @classmethod
    def build_power_off(cls) -> bytes:
        """Build protocol bytes to turn the unit off.

        :return: Encoded protocol bytes (7 bytes).
        """
        return cls._encode_short(CMD_TURN_OFF)

    @classmethod
    def build_command(cls, state: FujitsuACState) -> bytes:
        """Build the appropriate protocol bytes for the current state.

        Returns a power-off short message when *power* is ``False``, or
        a full state message when *power* is ``True``.

        :param state: Desired AC state.
        :return: Encoded protocol bytes.
        """
        if not state.power:
            return cls.build_power_off()
        return cls.build_power_on(state)

    @classmethod
    def build_off_timer(cls, state: FujitsuACState, minutes: int) -> bytes:
        """Build protocol bytes to turn the AC off after *minutes*.

        The AC must currently be on.  The full current state (mode, temp,
        fan, swing) is included in the command so the AC continues
        running with those settings until the timer expires.

        :param state: Current AC state (should have ``power=True``).
        :param minutes: Duration in minutes (1\u2013720).
        :return: Encoded protocol bytes.
        :raises ValueError: If *minutes* is out of range.
        """
        if not 1 <= minutes <= TIMER_MAX:
            raise ValueError(
                f"Off timer minutes must be 1\u2013{TIMER_MAX}, got {minutes}"
            )
        timer_state = FujitsuACState(
            power=True,
            mode=state.mode,
            temperature=state.temperature,
            fan=state.fan,
            swing=state.swing,
            outside_quiet=state.outside_quiet,
            device_id=state.device_id,
            protocol=state.protocol,
            timer_type=TIMER_OFF,
            off_timer_minutes=minutes,
        )
        return cls._encode_long(timer_state, power_on=False)

    @classmethod
    def build_on_timer(cls, state: FujitsuACState, minutes: int) -> bytes:
        """Build protocol bytes to turn the AC on after *minutes*.

        The desired state (mode, temp, fan, swing) to activate when the
        timer fires is taken from *state*.

        :param state: Desired AC state for when the timer fires.
        :param minutes: Duration in minutes (1\u2013720).
        :return: Encoded protocol bytes.
        :raises ValueError: If *minutes* is out of range.
        """
        if not 1 <= minutes <= TIMER_MAX:
            raise ValueError(
                f"On timer minutes must be 1\u2013{TIMER_MAX}, got {minutes}"
            )
        timer_state = FujitsuACState(
            power=True,
            mode=state.mode,
            temperature=state.temperature,
            fan=state.fan,
            swing=state.swing,
            outside_quiet=state.outside_quiet,
            device_id=state.device_id,
            protocol=state.protocol,
            timer_type=TIMER_ON,
            on_timer_minutes=minutes,
        )
        return cls._encode_long(timer_state, power_on=True)

    @classmethod
    def build_sleep_timer(cls, state: FujitsuACState, minutes: int) -> bytes:
        """Build protocol bytes to activate the sleep timer.

        The sleep timer turns the AC off after *minutes* with gradual
        comfort adjustments (the AC unit manages the wind-down).

        :param state: Current AC state (should have ``power=True``).
        :param minutes: Duration in minutes (1\u2013720).
        :return: Encoded protocol bytes.
        :raises ValueError: If *minutes* is out of range.
        """
        if not 1 <= minutes <= TIMER_MAX:
            raise ValueError(
                f"Sleep timer minutes must be 1\u2013{TIMER_MAX}, got {minutes}"
            )
        timer_state = FujitsuACState(
            power=True,
            mode=state.mode,
            temperature=state.temperature,
            fan=state.fan,
            swing=state.swing,
            outside_quiet=state.outside_quiet,
            device_id=state.device_id,
            protocol=state.protocol,
            timer_type=TIMER_SLEEP,
            off_timer_minutes=minutes,
        )
        return cls._encode_long(timer_state, power_on=False)

    @classmethod
    def build_cancel_timer(cls, state: FujitsuACState) -> bytes:
        """Build protocol bytes to cancel any active timer.

        Sends the current state with timer_type set to TIMER_STOP.

        :param state: Current AC state.
        :return: Encoded protocol bytes.
        """
        timer_state = FujitsuACState(
            power=state.power,
            mode=state.mode,
            temperature=state.temperature,
            fan=state.fan,
            swing=state.swing,
            outside_quiet=state.outside_quiet,
            device_id=state.device_id,
            protocol=state.protocol,
            timer_type=TIMER_STOP,
        )
        if not timer_state.power:
            return cls.build_power_off()
        return cls._encode_long(timer_state, power_on=False)

    # =========================================================================
    # Timing conversion
    # =========================================================================

    @classmethod
    def build_command_timings(cls, state: FujitsuACState) -> list[int]:
        """Build raw IR timings for the current state.

        Convenience method combining :meth:`build_command` and
        :meth:`bytes_to_timings`.

        :param state: Desired AC state.
        :return: Alternating mark/space durations in microseconds.
        """
        return cls.bytes_to_timings(cls.build_command(state))

    @staticmethod
    def bytes_to_timings(data: bytes) -> list[int]:
        """Encode protocol bytes into raw IR timing values.

        The output is an alternating sequence of mark/space durations
        in microseconds, suitable for any IR blaster that accepts raw
        timing arrays.

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
        data[9] |= (state.timer_type & 0x03) << 4

        # Byte 10: Fan (bits 2:0), Swing (bits 5:4)
        data[10] = (state.fan & 0x07) | ((state.swing & 0x03) << 4)

        # Bytes 11-13: Timers
        #   OffTimer (11 bits) | OffTimerEnable (1 bit) |
        #   OnTimer (11 bits)  | OnTimerEnable (1 bit)
        off_val = min(TIMER_MAX, max(0, state.off_timer_minutes))
        on_val = min(TIMER_MAX, max(0, state.on_timer_minutes))
        off_enable = state.timer_type in (TIMER_OFF, TIMER_SLEEP) and off_val > 0
        on_enable = state.timer_type == TIMER_ON and on_val > 0

        data[11] = off_val & 0xFF
        data[12] = (
            ((off_val >> 8) & 0x07)
            | ((1 << 3) if off_enable else 0)
            | ((on_val & 0x0F) << 4)
        )
        data[13] = (
            ((on_val >> 4) & 0x7F)
            | ((1 << 7) if on_enable else 0)
        )

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

            # Timer
            state.timer_type = (data[9] >> 4) & 0x03
            off_timer = (data[11] & 0xFF) | ((data[12] & 0x07) << 8)
            on_timer = ((data[12] >> 4) & 0x0F) | ((data[13] & 0x7F) << 4)
            if state.timer_type in (TIMER_OFF, TIMER_SLEEP):
                state.off_timer_minutes = off_timer
            elif state.timer_type == TIMER_ON:
                state.on_timer_minutes = on_timer
        elif cmd_byte == CMD_TURN_OFF:
            state.power = False

        return state

    # =========================================================================
    # Broadlink IR Format Conversion (backward compatibility)
    # =========================================================================

    @classmethod
    def bytes_to_broadlink(cls, data: bytes) -> str:
        """Convert protocol bytes to Broadlink base64 via IR timings.

        Convenience method for callers that still need the Broadlink
        format directly.  New code should use :meth:`bytes_to_timings`
        with an appropriate :class:`~.ir_transport.IRTransport`.

        :param data: Fujitsu AC protocol bytes.
        :return: Base64-encoded Broadlink IR code.
        """
        timings = cls.bytes_to_timings(data)
        return cls._timings_to_broadlink(timings)

    @staticmethod
    def _timings_to_broadlink(timings_us: list[int], repeat: int = 0) -> str:
        """Encode raw timing values into Broadlink base64 format.

        .. note::

           This duplicates :meth:`ir_transport.BroadlinkTransport.timings_to_broadlink`
           to avoid a protocol-layer → transport-layer import dependency.
           Kept for backward-compatibility callers of :meth:`bytes_to_broadlink`.

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
