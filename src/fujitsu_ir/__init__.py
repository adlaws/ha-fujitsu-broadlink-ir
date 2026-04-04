"""Fujitsu AC IR Protocol Library.

Encodes and decodes Fujitsu air conditioner IR commands,
with support for Broadlink IR blaster format conversion.
"""

from __future__ import annotations

from .broadlink import BroadlinkIR
from .const import (
    CMD_STEP_HORIZ,
    CMD_STEP_VERT,
    CMD_STAY_ON,
    CMD_TOGGLE_SWING_HORIZ,
    CMD_TOGGLE_SWING_VERT,
    CMD_TURN_OFF,
    CMD_TURN_ON,
    FAN_AUTO,
    FAN_HIGH,
    FAN_LOW,
    FAN_MED,
    FAN_QUIET,
    MAX_TEMP,
    MIN_TEMP,
    MODE_AUTO,
    MODE_COOL,
    MODE_DRY,
    MODE_FAN,
    MODE_HEAT,
    SWING_BOTH,
    SWING_HORIZ,
    SWING_OFF,
    SWING_VERT,
)
from .protocol import FujitsuAC, FujitsuACState

__all__ = [
    "FujitsuAC",
    "FujitsuACState",
    "BroadlinkIR",
    "MODE_AUTO",
    "MODE_COOL",
    "MODE_DRY",
    "MODE_FAN",
    "MODE_HEAT",
    "FAN_AUTO",
    "FAN_HIGH",
    "FAN_MED",
    "FAN_LOW",
    "FAN_QUIET",
    "SWING_OFF",
    "SWING_VERT",
    "SWING_HORIZ",
    "SWING_BOTH",
    "CMD_TURN_ON",
    "CMD_TURN_OFF",
    "CMD_STAY_ON",
    "CMD_TOGGLE_SWING_VERT",
    "CMD_TOGGLE_SWING_HORIZ",
    "CMD_STEP_VERT",
    "CMD_STEP_HORIZ",
    "MIN_TEMP",
    "MAX_TEMP",
]
