"""Broadlink IR Format Converter.

Converts between Broadlink's base64-encoded IR format and raw IR timing data,
and between raw timing data and Fujitsu AC protocol bytes.

Broadlink IR Format (after base64 decode):
  Byte 0:     0x26 (IR type marker)
  Byte 1:     Repeat count (0 = no repeat)
  Bytes 2-3:  Length of timing data (little-endian uint16)
  Bytes 4+:   Timing data (alternating mark/space durations)
  Trailer:    0x0D 0x05

Timing Data Encoding:
  Each timing value is in "ticks" where 1 tick ≈ 30.45 µs (8192/269 µs).
  - If byte != 0x00: the byte value IS the tick count
  - If byte == 0x00: the next 2 bytes are a big-endian uint16 tick count
  Values alternate between mark (IR on) and space (IR off), starting with mark.
"""

from __future__ import annotations

import base64

from .const import (
    BIT_MARK,
    BROADLINK_IR_TYPE,
    BROADLINK_TICK_US,
    HEADER_MARK,
    HEADER_SPACE,
    MIN_GAP,
    ONE_SPACE,
    ZERO_SPACE,
)


class BroadlinkIR:
    """Convert between Broadlink base64 IR codes and raw timing / protocol bytes."""

    # Thresholds for distinguishing timing values (in microseconds)
    HEADER_MARK_MIN = 2500
    HEADER_SPACE_MIN = 1200
    ONE_SPACE_MIN = 800  # Threshold between 0-space (~390µs) and 1-space (~1182µs)
    GAP_MIN = 5000       # Minimum gap duration indicating end of message

    # =========================================================================
    # Broadlink ↔ Raw Timing Conversion
    # =========================================================================

    @staticmethod
    def decode_base64(code: str) -> list[int]:
        """Decode a Broadlink base64 IR code into raw timing values.

        :param code: Base64-encoded Broadlink IR code.
        :return: Alternating mark/space durations in microseconds.
        :raises ValueError: If the code is too short or not an IR type.
        """
        raw = base64.b64decode(code)

        if len(raw) < 4:
            raise ValueError(f"Broadlink code too short: {len(raw)} bytes")

        if raw[0] != BROADLINK_IR_TYPE:
            raise ValueError(
                f"Not an IR code: type byte is 0x{raw[0]:02X} "
                f"(expected 0x{BROADLINK_IR_TYPE:02X})"
            )

        # Bytes 2-3: length of timing data (little-endian)
        data_len = raw[2] | (raw[3] << 8)

        # Extract timing values
        timings = []
        i = 4
        end = min(4 + data_len, len(raw))
        while i < end:
            if raw[i] == 0x00:
                # Next 2 bytes are big-endian uint16
                if i + 2 < end:
                    ticks = (raw[i + 1] << 8) | raw[i + 2]
                    i += 3
                else:
                    break
            else:
                ticks = raw[i]
                i += 1

            # Convert ticks to microseconds
            us = round(ticks * BROADLINK_TICK_US)
            timings.append(us)

        return timings

    @staticmethod
    def encode_base64(timings_us: list[int], repeat: int = 0) -> str:
        """Encode raw timing values into a Broadlink base64 IR code.

        :param timings_us: Alternating mark/space durations in microseconds.
        :param repeat: Number of times to repeat the signal (0 = none).
        :return: Base64-encoded Broadlink IR code string.
        """
        # Convert timings to ticks
        timing_bytes = bytearray()
        for us in timings_us:
            ticks = round(us / BROADLINK_TICK_US)
            if ticks > 255:
                timing_bytes.append(0x00)
                timing_bytes.append((ticks >> 8) & 0xFF)
                timing_bytes.append(ticks & 0xFF)
            else:
                timing_bytes.append(max(1, ticks))

        # Build complete Broadlink packet
        data_len = len(timing_bytes)
        packet = bytearray()
        packet.append(BROADLINK_IR_TYPE)
        packet.append(repeat & 0xFF)
        packet.append(data_len & 0xFF)
        packet.append((data_len >> 8) & 0xFF)
        packet.extend(timing_bytes)

        # Pad to even length and add end marker
        packet.append(0x0D)
        packet.append(0x05)

        return base64.b64encode(bytes(packet)).decode("ascii")

    # =========================================================================
    # Raw Timing ↔ Protocol Bytes Conversion
    # =========================================================================

    @classmethod
    def timings_to_bytes(cls, timings_us: list[int]) -> bytes:
        """Decode raw IR timing values into protocol bytes.

        Interprets the alternating mark/space pattern to extract bits,
        assembled LSB-first into bytes.

        :param timings_us: Alternating mark/space durations in microseconds.
        :return: Decoded protocol bytes.
        :raises ValueError: If the timing data is too short or has an
            invalid header.
        """
        if len(timings_us) < 4:
            raise ValueError("Timing data too short")

        # Verify header
        if timings_us[0] < cls.HEADER_MARK_MIN:
            raise ValueError(
                f"Header mark too short: {timings_us[0]}µs "
                f"(expected ≥{cls.HEADER_MARK_MIN}µs)"
            )
        if timings_us[1] < cls.HEADER_SPACE_MIN:
            raise ValueError(
                f"Header space too short: {timings_us[1]}µs "
                f"(expected ≥{cls.HEADER_SPACE_MIN}µs)"
            )

        # Extract bits from mark/space pairs after header
        bits = []
        i = 2  # Start after header mark + space
        while i + 1 < len(timings_us):
            mark = timings_us[i]
            space = timings_us[i + 1]

            # Check if mark is a bit mark (not a gap/trailer)
            if mark > cls.HEADER_MARK_MIN:
                break  # This is likely a repeat header or end

            # Check if space is a gap (end of message)
            if space > cls.GAP_MIN:
                break

            # Decode bit based on space duration
            if space > cls.ONE_SPACE_MIN:
                bits.append(1)
            else:
                bits.append(0)

            i += 2

        # Assemble bits into bytes (LSB first)
        result = bytearray()
        for byte_idx in range(0, len(bits), 8):
            byte_bits = bits[byte_idx:byte_idx + 8]
            if len(byte_bits) < 8:
                break  # Incomplete byte, discard

            byte_val = 0
            for bit_idx, bit in enumerate(byte_bits):
                byte_val |= (bit << bit_idx)

            result.append(byte_val)

        return bytes(result)

    @staticmethod
    def bytes_to_timings(data: bytes) -> list[int]:
        """Encode protocol bytes into raw IR timing values.

        Generate alternating mark/space durations for the given protocol
        bytes, using LSB-first bit ordering.

        :param data: Protocol bytes to encode.
        :return: Alternating mark/space durations in microseconds.
        """
        timings = []

        # Header
        timings.append(HEADER_MARK)
        timings.append(HEADER_SPACE)

        # Data bits (LSB first per byte)
        for byte_val in data:
            for bit_idx in range(8):
                bit = (byte_val >> bit_idx) & 1
                timings.append(BIT_MARK)
                timings.append(ONE_SPACE if bit else ZERO_SPACE)

        # Trailing mark
        timings.append(BIT_MARK)

        # Gap
        timings.append(MIN_GAP)

        return timings

    # =========================================================================
    # High-Level Convenience Methods
    # =========================================================================

    @classmethod
    def broadlink_to_bytes(cls, code: str) -> bytes:
        """Decode a Broadlink base64 code directly to protocol bytes.

        :param code: Base64-encoded Broadlink IR code.
        :return: Decoded Fujitsu AC protocol bytes.
        """
        timings = cls.decode_base64(code)
        return cls.timings_to_bytes(timings)

    @classmethod
    def bytes_to_broadlink(cls, data: bytes, repeat: int = 0) -> str:
        """Encode protocol bytes directly to a Broadlink base64 code.

        :param data: Fujitsu AC protocol bytes to encode.
        :param repeat: Number of times to repeat.
        :return: Base64-encoded Broadlink IR code.
        """
        timings = cls.bytes_to_timings(data)
        return cls.encode_base64(timings, repeat)
