"""Fujitsu AC IR Protocol Constants for Home Assistant integration.

Based on the IRremoteESP8266 project's analysis, adapted for the
AR-RWE3E remote (protocol ``0x31`` / ARREW4E family).
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

# =============================================================================
# Message Lengths (bytes)
# =============================================================================
STATE_LENGTH = 16
STATE_LENGTH_SHORT = 7

# =============================================================================
# Fixed Header Bytes
# =============================================================================
HEADER_BYTE0 = 0x14
HEADER_BYTE1 = 0x63
HEADER_BYTE3 = 0x10
HEADER_BYTE4 = 0x10

# =============================================================================
# Command Bytes
# =============================================================================
CMD_STAY_ON = 0x00
CMD_TURN_ON = 0x01
CMD_TURN_OFF = 0x02
CMD_ECONO = 0x09
CMD_POWERFUL = 0x39
CMD_STEP_VERT = 0x6C
CMD_TOGGLE_SWING_VERT = 0x6D
CMD_STEP_HORIZ = 0x79
CMD_TOGGLE_SWING_HORIZ = 0x7A
CMD_LONG_STATE = 0xFE

# =============================================================================
# Protocol Versions
# =============================================================================
PROTOCOL_STANDARD = 0x30
PROTOCOL_ARREW4E = 0x31  # AR-RWE3E / ARREW4E family

# =============================================================================
# AC Operating Modes
# =============================================================================
MODE_AUTO = 0x00
MODE_COOL = 0x01
MODE_DRY = 0x02
MODE_FAN = 0x03
MODE_HEAT = 0x04

# =============================================================================
# Fan Speeds
# =============================================================================
FAN_AUTO = 0x00
FAN_HIGH = 0x01
FAN_MED = 0x02
FAN_LOW = 0x03
FAN_QUIET = 0x04

# =============================================================================
# Swing Modes
# =============================================================================
SWING_OFF = 0x00
SWING_VERT = 0x01
SWING_HORIZ = 0x02
SWING_BOTH = 0x03

# =============================================================================
# Temperature
# =============================================================================
MIN_TEMP = 16.0
MAX_TEMP = 30.0
TEMP_STEP = 0.5

# =============================================================================
# Broadlink IR Format
# =============================================================================
BROADLINK_IR_TYPE = 0x26
BROADLINK_TICK_US = 8192.0 / 269.0  # ~30.45 µs per tick

# =============================================================================
# Home Assistant Config
# =============================================================================
DOMAIN = "fujitsu_ac_ir"
CONF_BROADLINK_DEVICE = "broadlink_device"
CONF_NAME = "name"
DEFAULT_NAME = "Fujitsu AC"
