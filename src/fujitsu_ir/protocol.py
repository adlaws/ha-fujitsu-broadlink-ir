"""Fujitsu AC IR Protocol Encoder/Decoder.

Handles encoding AC state into raw IR protocol bytes and decoding
raw bytes back into AC state. Supports both standard (0x30) protocol
models (ARRAH2E, etc.) and the 0x31 protocol (ARREW4E / AR-RWE3E family).

Protocol Reference (IRremoteESP8266):
  https://github.com/crankyoldgit/IRremoteESP8266/blob/master/src/ir_Fujitsu.h

Byte Layout — Short Message (7 bytes):
  Used for simple commands like power off, swing toggle, etc.
  ┌────────┬────────┬────────┬────────┬────────┬────────┬────────┐
  │ Byte 0 │ Byte 1 │ Byte 2 │ Byte 3 │ Byte 4 │ Byte 5 │ Byte 6 │
  │  0x14  │  0x63  │ ID/Dev │  0x10  │  0x10  │  Cmd   │  ~Cmd  │
  └────────┴────────┴────────┴────────┴────────┴────────┴────────┘

Byte Layout — Long Message (16 bytes):
  Used for full state commands (turn on, change settings).
  ┌────────┬────────┬────────┬────────┬────────┬────────┬────────┬────────┐
  │ Byte 0 │ Byte 1 │ Byte 2 │ Byte 3 │ Byte 4 │ Byte 5 │ Byte 6 │ Byte 7 │
  │  0x14  │  0x63  │ ID/Dev │  0x10  │  0x10  │  0xFE  │RestLen │Protocol│
  └────────┴────────┴────────┴────────┴────────┴────────┴────────┴────────┘
  ┌────────┬────────┬────────┬────────┬────────┬────────┬────────┬────────┐
  │ Byte 8 │ Byte 9 │Byte 10 │Byte 11 │Byte 12 │Byte 13 │Byte 14 │Byte 15 │
  │Pwr/Tmp │Md/Tmr  │Fan/Swg │ Timer  │ Timer  │ Timer  │Flt/Ext │Checksum│
  └────────┴────────┴────────┴────────┴────────┴────────┴────────┴────────┘

  Byte 8:  [7:2]=Temp  [1]=Fahrenheit  [0]=Power
  Byte 9:  [7:6]=0     [5:4]=TimerType [3]=Clean    [2:0]=Mode
  Byte 10: [7:6]=0     [5:4]=Swing     [3]=0        [2:0]=Fan
  Byte 11-13: Timer values (OffTimer 11 bits, OffTimerEnable 1 bit,
              OnTimer 11 bits, OnTimerEnable 1 bit)
  Byte 14: [7]=OutsideQuiet [6]=0 [5]=Unknown(=1) [4]=0 [3]=Filter [2:0]=0
  Byte 15: Checksum (such that sum of bytes 7-15 == 0 mod 256)

Bits are transmitted LSB first.
"""

from __future__ import annotations

from dataclasses import dataclass

from .const import (
    CMD_ECONO,
    CMD_LONG_STATE,
    CMD_NAMES,
    CMD_POWERFUL,
    CMD_STAY_ON,
    CMD_STEP_HORIZ,
    CMD_STEP_VERT,
    CMD_TOGGLE_SWING_HORIZ,
    CMD_TOGGLE_SWING_VERT,
    CMD_TURN_OFF,
    CMD_TURN_ON,
    FAN_AUTO,
    FAN_NAMES,
    HEADER_BYTE0,
    HEADER_BYTE1,
    HEADER_BYTE3,
    HEADER_BYTE4,
    MAX_TEMP,
    MIN_TEMP,
    MODE_COOL,
    MODE_NAMES,
    PROTOCOL_ARREW4E,
    STATE_LENGTH,
    STATE_LENGTH_SHORT,
    SWING_NAMES,
    SWING_OFF,
    TEMP_OFFSET_C,
    TIMER_MAX,
    TIMER_NAMES,
    TIMER_OFF,
    TIMER_ON,
    TIMER_SLEEP,
    TIMER_STOP,
)


# Short commands that don't carry full state
SHORT_COMMANDS = {
    CMD_TURN_OFF,
    CMD_ECONO,
    CMD_POWERFUL,
    CMD_STEP_VERT,
    CMD_TOGGLE_SWING_VERT,
    CMD_STEP_HORIZ,
    CMD_TOGGLE_SWING_HORIZ,
}


@dataclass
class FujitsuACState:
    """Represent the full state of a Fujitsu AC unit.

    Defaults to power-on so that constructing a ``FujitsuACState`` and
    encoding it produces a valid turn-on command.  Set ``power=False``
    explicitly when constructing a state that should not power the unit on.

    :param power: Whether the unit is on.
    :param mode: Operating mode (see ``MODE_*`` constants).
    :param temperature: Target temperature in °C.
    :param fan: Fan speed (see ``FAN_*`` constants).
    :param swing: Swing mode (see ``SWING_*`` constants).
    :param outside_quiet: Enable outside-unit quiet mode.
    :param filter_active: Enable filter mode.
    :param clean: Enable clean mode.
    :param device_id: Remote device ID (0–3).
    :param protocol: Protocol version byte (``0x31`` for AR-RWE3E / ARREW4E,
        ``0x30`` for standard models).
    :param timer_type: Timer mode (``TIMER_STOP``, ``TIMER_SLEEP``,
        ``TIMER_OFF``, ``TIMER_ON``).  Only one timer can be active.
    :param off_timer_minutes: Duration in minutes for the off or sleep timer
        (0–720).  Also used when ``timer_type`` is ``TIMER_SLEEP``.
    :param on_timer_minutes: Duration in minutes for the on timer (0–720).
    """

    power: bool = True
    mode: int = MODE_COOL
    temperature: float = 24.0
    fan: int = FAN_AUTO
    swing: int = SWING_OFF
    outside_quiet: bool = False
    filter_active: bool = False
    clean: bool = False
    device_id: int = 0
    protocol: int = PROTOCOL_ARREW4E
    timer_type: int = TIMER_STOP
    off_timer_minutes: int = 0
    on_timer_minutes: int = 0

    def __str__(self) -> str:
        """Return a human-readable summary of the AC state.

        :return: Formatted string showing power, mode, temperature, fan,
            and swing settings.
        """
        return (
            f"Power={'ON' if self.power else 'OFF'}, "
            f"Mode={MODE_NAMES.get(self.mode, f'?{self.mode}')}, "
            f"Temp={self.temperature}°C, "
            f"Fan={FAN_NAMES.get(self.fan, f'?{self.fan}')}, "
            f"Swing={SWING_NAMES.get(self.swing, f'?{self.swing}')}"
        )


class FujitsuAC:
    """Encode and decode Fujitsu AC IR protocol messages.

    Supports both the standard (``0x30``) protocol and the AR-RWE3E /
    ARREW4E family (``0x31``).

    :param state: Initial AC state.  Defaults to a new ``FujitsuACState``.
    """

    def __init__(self, state: FujitsuACState | None = None) -> None:
        self.state: FujitsuACState = state or FujitsuACState()
        self._command: int = CMD_TURN_ON

    @property
    def command(self) -> int:
        """Return the current command byte.

        :return: Command byte value (see ``CMD_*`` constants).
        """
        return self._command

    @command.setter
    def command(self, cmd: int) -> None:
        """Set the current command byte.

        :param cmd: Command byte value (see ``CMD_*`` constants).
        """
        self._command = cmd

    # =========================================================================
    # Encoding
    # =========================================================================

    def encode(self) -> bytes:
        """Encode the current state into IR protocol bytes.

        :return: A 16-byte state message for turn-on / state-change commands,
            or a 7-byte short message for off/special commands.
        """
        if self._command in SHORT_COMMANDS:
            return self._encode_short(self._command)
        return self._encode_long()

    def encode_off(self) -> bytes:
        """Encode a power-off command (short 7-byte message).

        :return: Encoded 7-byte short message.
        """
        return self._encode_short(CMD_TURN_OFF)

    def encode_on(self) -> bytes:
        """Encode a power-on command with the current full state.

        :return: Encoded 16-byte state message.
        """
        self._command = CMD_TURN_ON
        return self._encode_long()

    def encode_state(self) -> bytes:
        """Encode a 'stay on' state change (full 16-byte message).

        Use this when changing settings while the AC is already on.

        :return: Encoded 16-byte state message.
        """
        self._command = CMD_STAY_ON
        return self._encode_long()

    def _encode_short(self, cmd: int) -> bytes:
        """Build a 7-byte short command message.

        :param cmd: The command byte to send.
        :return: Encoded 7-byte message.
        """
        data = bytearray(STATE_LENGTH_SHORT)
        data[0] = HEADER_BYTE0
        data[1] = HEADER_BYTE1
        data[2] = (self.state.device_id & 0x03) << 4
        data[3] = HEADER_BYTE3
        data[4] = HEADER_BYTE4
        data[5] = cmd
        data[6] = (~cmd) & 0xFF
        return bytes(data)

    def _encode_long(self) -> bytes:
        """Build a 16-byte full state message.

        :return: Encoded 16-byte message containing the full AC state.
        """
        data = bytearray(STATE_LENGTH)

        # Fixed header (bytes 0-4)
        data[0] = HEADER_BYTE0
        data[1] = HEADER_BYTE1
        data[2] = (self.state.device_id & 0x03) << 4
        data[3] = HEADER_BYTE3
        data[4] = HEADER_BYTE4

        # Byte 5: Long command indicator
        data[5] = CMD_LONG_STATE  # 0xFE

        # Byte 6: RestLength — number of bytes after this one
        data[6] = STATE_LENGTH - 7  # = 9

        # Byte 7: Protocol version
        data[7] = self.state.protocol

        # Byte 8: Power (bit 0), Fahrenheit (bit 1), Temperature (bits 7:2)
        temp_clamped = max(MIN_TEMP, min(MAX_TEMP, self.state.temperature))
        if self.state.protocol == PROTOCOL_ARREW4E:
            # ARREW4E: temp_raw = (temp_C - 8) * 2
            temp_encoded = int((temp_clamped - 8.0) * 2) & 0x3F
        else:
            # Standard: temp_raw = (temp_C - 16) * 4
            temp_encoded = int((temp_clamped - TEMP_OFFSET_C) * 4) & 0x3F
        power_bit = 1 if (self._command == CMD_TURN_ON or self.state.power) else 0
        data[8] = (temp_encoded << 2) | (0 << 1) | power_bit

        # Byte 9: Mode (bits 2:0), Clean (bit 3), TimerType (bits 5:4)
        data[9] = self.state.mode & 0x07
        if self.state.clean:
            data[9] |= (1 << 3)
        data[9] |= (self.state.timer_type & 0x03) << 4

        # Byte 10: Fan (bits 2:0), Swing (bits 5:4)
        data[10] = (self.state.fan & 0x07) | ((self.state.swing & 0x03) << 4)

        # Bytes 11-13: Timers
        #   OffTimer (11 bits) | OffTimerEnable (1 bit) |
        #   OnTimer (11 bits)  | OnTimerEnable (1 bit)
        off_val = min(TIMER_MAX, max(0, self.state.off_timer_minutes))
        on_val = min(TIMER_MAX, max(0, self.state.on_timer_minutes))
        off_enable = self.state.timer_type in (TIMER_OFF, TIMER_SLEEP) and off_val > 0
        on_enable = self.state.timer_type == TIMER_ON and on_val > 0

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

        # Byte 14: Filter (bit 3), Unknown=1 (bit 5), OutsideQuiet (bit 7)
        #   Bit 0 is always set on ARREW4E / AR-RWE3E protocol (0x31)
        data[14] = (1 << 5)  # Unknown bit is always 1
        if self.state.protocol == PROTOCOL_ARREW4E:
            data[14] |= 0x01  # Bit 0 always set on this model family
        if self.state.filter_active:
            data[14] |= (1 << 3)
        if self.state.outside_quiet:
            data[14] |= (1 << 7)

        # Byte 15: Checksum — sum of bytes[7:16] must be 0 mod 256
        checksum = sum(data[7:15]) & 0xFF
        data[15] = (256 - checksum) & 0xFF

        return bytes(data)

    @property
    def temperature(self) -> float:
        """Return the target temperature in °C.

        :return: Temperature in degrees Celsius.
        """
        return self.state.temperature

    @temperature.setter
    def temperature(self, temp: float) -> None:
        """Set the target temperature, clamped to the valid range.

        :param temp: Desired temperature in °C.
        """
        self.state.temperature = max(MIN_TEMP, min(MAX_TEMP, temp))

    # =========================================================================
    # Decoding
    # =========================================================================

    @classmethod
    def from_bytes(cls, data: bytes) -> FujitsuAC:
        """Decode raw IR protocol bytes into a FujitsuAC instance.

        :param data: Raw protocol bytes (7 or 16 bytes).
        :return: A ``FujitsuAC`` instance with decoded state.
        :raises ValueError: If the data is too short, has an invalid header,
            fails checksum, or is otherwise malformed.
        """
        if len(data) < STATE_LENGTH_SHORT:
            raise ValueError(
                f"Data too short: {len(data)} bytes (minimum {STATE_LENGTH_SHORT})"
            )

        # Validate header
        if data[0] != HEADER_BYTE0 or data[1] != HEADER_BYTE1:
            raise ValueError(
                f"Invalid header: 0x{data[0]:02X} 0x{data[1]:02X} "
                f"(expected 0x{HEADER_BYTE0:02X} 0x{HEADER_BYTE1:02X})"
            )

        ac = cls()
        ac.state.device_id = (data[2] >> 4) & 0x03

        # Determine if this is a short or long message
        cmd_byte = data[5]

        if cmd_byte in (CMD_LONG_STATE, 0xFC):
            # Long message — full state
            if len(data) < STATE_LENGTH:
                raise ValueError(
                    f"Long message too short: {len(data)} bytes "
                    f"(expected {STATE_LENGTH})"
                )

            # Verify checksum
            if not cls.verify_checksum(data):
                raise ValueError("Checksum mismatch")

            # Detect protocol version
            ac.state.protocol = data[7]

            # Byte 8: Power, Temp
            ac.state.power = bool(data[8] & 0x01)
            temp_encoded = (data[8] >> 2) & 0x3F
            if data[7] == PROTOCOL_ARREW4E:
                # ARREW4E: temp_C = temp_raw / 2 + 8
                ac.state.temperature = (temp_encoded / 2.0) + 8.0
            else:
                # Standard: temp_C = temp_raw / 4 + 16
                ac.state.temperature = (temp_encoded / 4.0) + TEMP_OFFSET_C

            if ac.state.power:
                ac._command = CMD_TURN_ON
            else:
                ac._command = CMD_STAY_ON

            # Byte 9: Mode, Clean, TimerType
            ac.state.mode = data[9] & 0x07
            ac.state.clean = bool(data[9] & (1 << 3))
            ac.state.timer_type = (data[9] >> 4) & 0x03

            # Byte 10: Fan, Swing
            ac.state.fan = data[10] & 0x07
            ac.state.swing = (data[10] >> 4) & 0x03

            # Bytes 11-13: Timers
            off_timer = (data[11] & 0xFF) | ((data[12] & 0x07) << 8)
            on_timer = ((data[12] >> 4) & 0x0F) | ((data[13] & 0x7F) << 4)
            if ac.state.timer_type in (TIMER_OFF, TIMER_SLEEP):
                ac.state.off_timer_minutes = off_timer
            elif ac.state.timer_type == TIMER_ON:
                ac.state.on_timer_minutes = on_timer

            # Byte 14: Filter, OutsideQuiet
            ac.state.filter_active = bool(data[14] & (1 << 3))
            ac.state.outside_quiet = bool(data[14] & (1 << 7))

        else:
            # Short message — simple command
            ac._command = cmd_byte
            ac.state.power = (cmd_byte != CMD_TURN_OFF)

        return ac

    @staticmethod
    def verify_checksum(data: bytes) -> bool:
        """Verify the checksum of a long (16-byte) message.

        The checksum is valid when ``sum(bytes[7:16]) == 0 (mod 256)``.

        :param data: Raw protocol bytes.
        :return: ``True`` if valid, ``False`` otherwise.
        """
        if len(data) < STATE_LENGTH:
            # Short messages use an inverse byte (byte 6 = ~byte 5), not a
            # sum checksum.  Return True here so callers can unconditionally
            # call verify_checksum(); use verify_short_checksum() for the
            # inverse-byte check on short messages.
            return True

        checksum_range = data[STATE_LENGTH_SHORT:STATE_LENGTH]
        return (sum(checksum_range) & 0xFF) == 0

    @staticmethod
    def verify_short_checksum(data: bytes) -> bool:
        """Verify the checksum of a short (7-byte) message.

        Byte 6 must be the bitwise inverse of byte 5.

        :param data: Raw protocol bytes.
        :return: ``True`` if valid, ``False`` otherwise.
        """
        if len(data) < STATE_LENGTH_SHORT:
            return False
        return data[6] == ((~data[5]) & 0xFF)

    # =========================================================================
    # Pretty Printing
    # =========================================================================

    def describe(self) -> str:
        """Return a human-readable description of the current state/command.

        :return: Multi-line formatted string describing the command and state.
        """
        lines = []

        if self._command in SHORT_COMMANDS or self._command == CMD_TURN_OFF:
            cmd_name = CMD_NAMES.get(self._command, f"Unknown(0x{self._command:02X})")
            lines.append(f"Command: {cmd_name}")
        else:
            lines.append(f"Command: {'Turn On' if self._command == CMD_TURN_ON else 'State Change'}")
            lines.append(f"  Power:  {'ON' if self.state.power else 'OFF'}")
            lines.append(f"  Mode:   {MODE_NAMES.get(self.state.mode, f'Unknown({self.state.mode})')}")
            lines.append(f"  Temp:   {self.state.temperature}°C")
            lines.append(f"  Fan:    {FAN_NAMES.get(self.state.fan, f'Unknown({self.state.fan})')}")
            lines.append(f"  Swing:  {SWING_NAMES.get(self.state.swing, f'Unknown({self.state.swing})')}")
            if self.state.outside_quiet:
                lines.append("  Outside Quiet: ON")
            if self.state.filter_active:
                lines.append("  Filter: ON")
            if self.state.clean:
                lines.append("  Clean:  ON")
            if self.state.timer_type != TIMER_STOP:
                timer_name = TIMER_NAMES.get(
                    self.state.timer_type, f"Unknown({self.state.timer_type})"
                )
                if self.state.timer_type in (TIMER_OFF, TIMER_SLEEP):
                    mins = self.state.off_timer_minutes
                else:
                    mins = self.state.on_timer_minutes
                lines.append(
                    f"  Timer:  {timer_name} {mins // 60:02d}:{mins % 60:02d}"
                )

        return "\n".join(lines)

    @staticmethod
    def bytes_to_hex(data: bytes) -> str:
        """Format bytes as a space-separated hex string.

        :param data: Raw bytes.
        :return: Hex string (e.g. ``"14 63 00 10 10 02 FD"``).
        """
        return " ".join(f"{b:02X}" for b in data)

    @staticmethod
    def describe_bytes(data: bytes) -> str:
        """Return a detailed byte-by-byte description of raw IR data.

        :param data: Raw protocol bytes (7 or 16 bytes).
        :return: Multi-line human-readable description.
        """
        lines = []
        hex_str = " ".join(f"{b:02X}" for b in data)
        lines.append(f"Raw bytes ({len(data)}): {hex_str}")

        if len(data) >= STATE_LENGTH_SHORT:
            lines.append(f"  [0-1] Header:    0x{data[0]:02X} 0x{data[1]:02X}")
            lines.append(f"  [2]   Device ID: {(data[2] >> 4) & 0x03}")
            lines.append(f"  [3-4] Fixed:     0x{data[3]:02X} 0x{data[4]:02X}")
            lines.append(f"  [5]   Command:   0x{data[5]:02X} ({CMD_NAMES.get(data[5], 'Unknown')})")

        if len(data) == STATE_LENGTH_SHORT:
            lines.append(f"  [6]   Inverse:   0x{data[6]:02X} (valid={data[6] == (~data[5] & 0xFF)})")

        elif len(data) >= STATE_LENGTH:
            lines.append(f"  [6]   RestLen:   {data[6]}")
            lines.append(f"  [7]   Protocol:  0x{data[7]:02X}")

            power = bool(data[8] & 0x01)
            fahrenheit = bool(data[8] & 0x02)
            temp_raw = (data[8] >> 2) & 0x3F
            if data[7] == PROTOCOL_ARREW4E:
                temp_c = (temp_raw / 2.0) + 8.0
            else:
                temp_c = (temp_raw / 4.0) + TEMP_OFFSET_C
            lines.append(f"  [8]   Power:     {'ON' if power else 'OFF'}")
            lines.append(f"         Fahrenheit:{fahrenheit}")
            lines.append(f"         Temp raw:  {temp_raw} → {temp_c}°C")

            mode = data[9] & 0x07
            clean = bool(data[9] & 0x08)
            timer_type = (data[9] >> 4) & 0x03
            lines.append(f"  [9]   Mode:      {mode} ({MODE_NAMES.get(mode, '?')})")
            lines.append(f"         Clean:     {clean}")
            lines.append(f"         TimerType: {timer_type} ({TIMER_NAMES.get(timer_type, '?')})")

            fan = data[10] & 0x07
            swing = (data[10] >> 4) & 0x03
            lines.append(f"  [10]  Fan:       {fan} ({FAN_NAMES.get(fan, '?')})")
            lines.append(f"         Swing:     {swing} ({SWING_NAMES.get(swing, '?')})")

            lines.append(f"  [11-13] Timers:  0x{data[11]:02X} 0x{data[12]:02X} 0x{data[13]:02X}")
            off_timer = (data[11] & 0xFF) | ((data[12] & 0x07) << 8)
            off_enable = bool(data[12] & 0x08)
            on_timer = ((data[12] >> 4) & 0x0F) | ((data[13] & 0x7F) << 4)
            on_enable = bool(data[13] & 0x80)
            lines.append(f"         OffTimer:  {off_timer} min (enable={off_enable})")
            lines.append(f"         OnTimer:   {on_timer} min (enable={on_enable})")

            filter_on = bool(data[14] & 0x08)
            unknown = bool(data[14] & 0x20)
            outside_quiet = bool(data[14] & 0x80)
            lines.append(f"  [14]  Filter:    {filter_on}")
            lines.append(f"         Unknown:   {unknown}")
            lines.append(f"         OutQuiet:  {outside_quiet}")

            chk_valid = (sum(data[7:16]) & 0xFF) == 0
            lines.append(f"  [15]  Checksum:  0x{data[15]:02X} (valid={chk_valid})")

        return "\n".join(lines)
