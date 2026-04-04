"""Fujitsu AC IR Protocol Constants.

Based on the IRremoteESP8266 project's analysis of the Fujitsu AC protocol.
See: https://github.com/crankyoldgit/IRremoteESP8266/blob/master/src/ir_Fujitsu.h
"""

from __future__ import annotations

# =============================================================================
# IR Signal Timing (microseconds)
# =============================================================================
HEADER_MARK = 3324
HEADER_SPACE = 1574
BIT_MARK = 448
ONE_SPACE = 1182
ZERO_SPACE = 390
MIN_GAP = 8100
CARRIER_FREQ_KHZ = 38

# =============================================================================
# Message Lengths (bytes)
# =============================================================================
STATE_LENGTH = 16        # Long message (ARRAH2E, ARRY4, ARREB1E)
STATE_LENGTH_SHORT = 7   # Short message (ARRAH2E, ARRY4, ARREB1E)
# ARDB1/ARJW2 use STATE_LENGTH - 1 and STATE_LENGTH_SHORT - 1

# =============================================================================
# Fixed Header Bytes
# =============================================================================
HEADER_BYTE0 = 0x14
HEADER_BYTE1 = 0x63
HEADER_BYTE3 = 0x10
HEADER_BYTE4 = 0x10

# =============================================================================
# Command Bytes (Byte 5 in short messages)
# =============================================================================
CMD_STAY_ON = 0x00            # No change / keepalive
CMD_TURN_ON = 0x01            # Turn on
CMD_TURN_OFF = 0x02           # Turn off
CMD_ECONO = 0x09              # Economy mode
CMD_POWERFUL = 0x39           # Powerful/turbo mode
CMD_STEP_VERT = 0x6C          # Step vertical swing
CMD_TOGGLE_SWING_VERT = 0x6D  # Toggle vertical swing
CMD_STEP_HORIZ = 0x79         # Step horizontal swing
CMD_TOGGLE_SWING_HORIZ = 0x7A # Toggle horizontal swing

# Long command indicator in Byte 5
CMD_LONG_STATE = 0xFE  # ARRAH2E / ARRY4 / ARREB1E
CMD_LONG_STATE_ALT = 0xFC  # ARDB1 / ARJW2

# Command descriptions for display
CMD_NAMES = {
    CMD_STAY_ON: "Stay On",
    CMD_TURN_ON: "Turn On",
    CMD_TURN_OFF: "Turn Off",
    CMD_ECONO: "Economy",
    CMD_POWERFUL: "Powerful",
    CMD_STEP_VERT: "Step Vertical",
    CMD_TOGGLE_SWING_VERT: "Toggle Swing Vertical",
    CMD_STEP_HORIZ: "Step Horizontal",
    CMD_TOGGLE_SWING_HORIZ: "Toggle Swing Horizontal",
    CMD_LONG_STATE: "Full State (Long)",
    CMD_LONG_STATE_ALT: "Full State (Long/Alt)",
}

# =============================================================================
# Protocol Version (Byte 7 in long messages)
# =============================================================================
PROTOCOL_STANDARD = 0x30  # Most models (ARRAH2E, ARDB1, etc.)
PROTOCOL_ARREW4E = 0x31   # ARREW4E / AR-RWE3E family

# =============================================================================
# AC Operating Modes (3 bits, Byte 9 bits 2:0)
# =============================================================================
MODE_AUTO = 0x00  # 0b000
MODE_COOL = 0x01  # 0b001
MODE_DRY = 0x02   # 0b010
MODE_FAN = 0x03   # 0b011
MODE_HEAT = 0x04  # 0b100

MODE_NAMES = {
    MODE_AUTO: "Auto",
    MODE_COOL: "Cool",
    MODE_DRY: "Dry",
    MODE_FAN: "Fan Only",
    MODE_HEAT: "Heat",
}

# =============================================================================
# Fan Speeds (3 bits, Byte 10 bits 2:0)
# =============================================================================
FAN_AUTO = 0x00   # Automatic
FAN_HIGH = 0x01   # High
FAN_MED = 0x02    # Medium
FAN_LOW = 0x03    # Low
FAN_QUIET = 0x04  # Quiet

FAN_NAMES = {
    FAN_AUTO: "Auto",
    FAN_HIGH: "High",
    FAN_MED: "Medium",
    FAN_LOW: "Low",
    FAN_QUIET: "Quiet",
}

# =============================================================================
# Swing Modes (2 bits, Byte 10 bits 5:4)
# =============================================================================
SWING_OFF = 0x00    # No swing
SWING_VERT = 0x01   # Vertical swing
SWING_HORIZ = 0x02  # Horizontal swing
SWING_BOTH = 0x03   # Both vertical and horizontal

SWING_NAMES = {
    SWING_OFF: "Off",
    SWING_VERT: "Vertical",
    SWING_HORIZ: "Horizontal",
    SWING_BOTH: "Both",
}

# =============================================================================
# Timer Types (2 bits, Byte 9 bits 5:4)
# =============================================================================
TIMER_STOP = 0x00     # Stop all timers
TIMER_SLEEP = 0x01    # Sleep timer
TIMER_OFF = 0x02      # Off timer
TIMER_ON = 0x03       # On timer

# =============================================================================
# Temperature
# =============================================================================
MIN_TEMP = 16.0   # Minimum temperature (°C)
MAX_TEMP = 30.0   # Maximum temperature (°C)
TEMP_STEP = 0.5   # Temperature step (°C) — 0.5° resolution
TEMP_OFFSET_C = 16  # Offset for Celsius encoding (= MIN_TEMP)

# For Fahrenheit (ARREW4E only)
MIN_TEMP_F = 60.0
MAX_TEMP_F = 88.0
TEMP_OFFSET_F = 44

# =============================================================================
# Broadlink IR Format
# =============================================================================
BROADLINK_IR_TYPE = 0x26
BROADLINK_TICK_US = 8192.0 / 269.0  # ~30.45 microseconds per tick
