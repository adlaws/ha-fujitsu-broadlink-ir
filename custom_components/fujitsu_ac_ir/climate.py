"""Fujitsu AC IR climate platform.

Provides a Home Assistant Climate entity that controls a Fujitsu air conditioner
via an IR blaster. Commands are assembled from the decoded Fujitsu IR
protocol (AR-RWE3E / ARREW4E family, protocol 0x31).

Each command sent encodes the FULL desired AC state (mode, temp, fan, swing),
not just the changed setting — matching how the physical remote works.

Timer services (set_off_timer, set_on_timer, set_sleep_timer, cancel_timer)
are registered as entity services on this platform.
"""

from __future__ import annotations

import datetime
import logging
from typing import Any

import voluptuous as vol

from homeassistant.components.climate import (
    ClimateEntity,
    ClimateEntityFeature,
    HVACMode,
)
from homeassistant.components.climate.const import (
    FAN_AUTO,
    FAN_HIGH,
    FAN_LOW,
    FAN_MEDIUM,
    SWING_BOTH,
    SWING_HORIZONTAL,
    SWING_OFF,
    SWING_VERTICAL,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import ATTR_TEMPERATURE, UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import (
    AddEntitiesCallback,
    async_get_current_platform,
)
from homeassistant.util import dt as dt_util

from . import FujitsuACIRData, async_send_ir_bytes, async_send_ir_command
from .const import (
    CONF_NAME,
    DEFAULT_NAME,
    DOMAIN,
    FAN_AUTO as IR_FAN_AUTO,
    FAN_HIGH as IR_FAN_HIGH,
    FAN_LOW as IR_FAN_LOW,
    FAN_MED as IR_FAN_MED,
    FAN_QUIET as IR_FAN_QUIET,
    MAX_TEMP,
    MIN_TEMP,
    MODE_AUTO as IR_MODE_AUTO,
    MODE_COOL as IR_MODE_COOL,
    MODE_DRY as IR_MODE_DRY,
    MODE_FAN as IR_MODE_FAN,
    MODE_HEAT as IR_MODE_HEAT,
    SWING_BOTH as IR_SWING_BOTH,
    SWING_HORIZ as IR_SWING_HORIZ,
    SWING_OFF as IR_SWING_OFF,
    SWING_VERT as IR_SWING_VERT,
    TEMP_STEP,
    TIMER_MAX,
    VERSION,
)
from .ir_codec import FujitsuACCodec

_LOGGER = logging.getLogger(__name__)

# =============================================================================
# Mapping tables: Home Assistant ↔ Fujitsu IR protocol
# =============================================================================

HVAC_MODE_TO_IR = {
    HVACMode.AUTO: IR_MODE_AUTO,
    HVACMode.COOL: IR_MODE_COOL,
    HVACMode.DRY: IR_MODE_DRY,
    HVACMode.FAN_ONLY: IR_MODE_FAN,
    HVACMode.HEAT: IR_MODE_HEAT,
}

IR_TO_HVAC_MODE = {v: k for k, v in HVAC_MODE_TO_IR.items()}

# Fan "quiet" mode exposed as a custom fan mode string
FAN_QUIET = "quiet"

FAN_MODE_TO_IR = {
    FAN_AUTO: IR_FAN_AUTO,
    FAN_HIGH: IR_FAN_HIGH,
    FAN_MEDIUM: IR_FAN_MED,
    FAN_LOW: IR_FAN_LOW,
    FAN_QUIET: IR_FAN_QUIET,
}

IR_TO_FAN_MODE = {v: k for k, v in FAN_MODE_TO_IR.items()}

SWING_MODE_TO_IR = {
    SWING_OFF: IR_SWING_OFF,
    SWING_VERTICAL: IR_SWING_VERT,
    SWING_HORIZONTAL: IR_SWING_HORIZ,
    SWING_BOTH: IR_SWING_BOTH,
}

IR_TO_SWING_MODE = {v: k for k, v in SWING_MODE_TO_IR.items()}

# =============================================================================
# Timer service constants
# =============================================================================

SERVICE_SET_OFF_TIMER = "set_off_timer"
SERVICE_SET_ON_TIMER = "set_on_timer"
SERVICE_SET_SLEEP_TIMER = "set_sleep_timer"
SERVICE_CANCEL_TIMER = "cancel_timer"

ATTR_MINUTES = "minutes"
ATTR_TIME = "time"

# Schema shared by off and sleep timer services
_TIMER_DURATION_SCHEMA = {
    vol.Optional(ATTR_MINUTES): vol.All(
        cv.positive_int, vol.Range(min=1, max=TIMER_MAX)
    ),
    vol.Optional(ATTR_TIME): cv.time,
}

# On timer may optionally override mode / temp / fan / swing
_ON_TIMER_SCHEMA = {
    **_TIMER_DURATION_SCHEMA,
    vol.Optional("mode"): vol.In(
        ["auto", "cool", "heat", "dry", "fan_only"]
    ),
    vol.Optional("temperature"): vol.All(
        vol.Coerce(float), vol.Range(min=MIN_TEMP, max=MAX_TEMP)
    ),
    vol.Optional("fan_mode"): vol.In(
        [FAN_AUTO, FAN_HIGH, FAN_MEDIUM, FAN_LOW, FAN_QUIET]
    ),
    vol.Optional("swing_mode"): vol.In(
        [SWING_OFF, SWING_VERTICAL, SWING_HORIZONTAL, SWING_BOTH]
    ),
}


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the Fujitsu AC IR climate entity from a config entry.

    :param hass: Home Assistant instance.
    :param config_entry: Config entry being set up.
    :param async_add_entities: Callback to register new entities.
    """
    name = config_entry.data.get(CONF_NAME, DEFAULT_NAME)
    data: FujitsuACIRData = hass.data[DOMAIN][config_entry.entry_id]

    async_add_entities(
        [FujitsuACClimate(config_entry.entry_id, name, data)],
        update_before_add=False,
    )

    # Register timer entity-services (once per platform setup)
    platform = async_get_current_platform()
    platform.async_register_entity_service(
        SERVICE_SET_OFF_TIMER,
        _TIMER_DURATION_SCHEMA,
        "async_set_off_timer",
    )
    platform.async_register_entity_service(
        SERVICE_SET_ON_TIMER,
        _ON_TIMER_SCHEMA,
        "async_set_on_timer",
    )
    platform.async_register_entity_service(
        SERVICE_SET_SLEEP_TIMER,
        _TIMER_DURATION_SCHEMA,
        "async_set_sleep_timer",
    )
    platform.async_register_entity_service(
        SERVICE_CANCEL_TIMER,
        {},
        "async_cancel_timer",
    )


class FujitsuACClimate(ClimateEntity):
    """Climate entity for Fujitsu AC controlled via IR blaster."""

    _attr_has_entity_name = True
    _attr_temperature_unit = UnitOfTemperature.CELSIUS
    _attr_precision = TEMP_STEP
    _attr_target_temperature_step = TEMP_STEP
    _attr_min_temp = MIN_TEMP
    _attr_max_temp = MAX_TEMP

    _attr_supported_features = (
        ClimateEntityFeature.TARGET_TEMPERATURE
        | ClimateEntityFeature.FAN_MODE
        | ClimateEntityFeature.SWING_MODE
    )

    _attr_hvac_modes = [
        HVACMode.OFF,
        HVACMode.AUTO,
        HVACMode.COOL,
        HVACMode.HEAT,
        HVACMode.DRY,
        HVACMode.FAN_ONLY,
    ]

    _attr_fan_modes = [FAN_AUTO, FAN_HIGH, FAN_MEDIUM, FAN_LOW, FAN_QUIET]
    _attr_swing_modes = [SWING_OFF, SWING_VERTICAL, SWING_HORIZONTAL, SWING_BOTH]

    def __init__(
        self,
        entry_id: str,
        name: str,
        data: FujitsuACIRData,
    ) -> None:
        """Initialize the climate entity.

        :param entry_id: Config entry unique ID.
        :param name: Display name for the entity.
        :param data: Shared integration runtime data.
        """
        self._data = data

        self._attr_unique_id = f"fujitsu_ac_ir_{entry_id}"
        self._attr_name = name
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry_id)},
            name=name,
            manufacturer="Fujitsu",
            model="AR-RWE3E / ARREW4E",
            sw_version=VERSION,
        )

        # Initial HA state
        self._attr_hvac_mode = HVACMode.OFF
        self._attr_target_temperature = 24.0
        self._attr_fan_mode = FAN_AUTO
        self._attr_swing_mode = SWING_OFF

    # =========================================================================
    # Actions
    # =========================================================================

    async def async_set_hvac_mode(self, hvac_mode: HVACMode) -> None:
        """Set HVAC mode (off, cool, heat, auto, dry, fan_only).

        :param hvac_mode: The desired HVAC operating mode.
        """
        if hvac_mode == HVACMode.OFF:
            self._attr_hvac_mode = HVACMode.OFF
            self._data.ir_state.power = False
            await self._send_ir()
        else:
            self._attr_hvac_mode = hvac_mode
            self._data.ir_state.power = True
            self._data.ir_state.mode = HVAC_MODE_TO_IR[hvac_mode]
            await self._send_ir()
        self.async_write_ha_state()

    async def async_set_temperature(self, **kwargs: Any) -> None:
        """Set target temperature.

        :param kwargs: Keyword arguments; expects ``ATTR_TEMPERATURE``.
        """
        temp = kwargs.get(ATTR_TEMPERATURE)
        if temp is None:
            return

        temp = round(
            max(MIN_TEMP, min(MAX_TEMP, round(temp / TEMP_STEP) * TEMP_STEP)),
            1,
        )
        self._attr_target_temperature = temp
        self._data.ir_state.temperature = temp

        # If currently off, turn on when setting temperature
        if self._attr_hvac_mode == HVACMode.OFF:
            self._attr_hvac_mode = HVACMode.AUTO
            self._data.ir_state.power = True
            self._data.ir_state.mode = IR_MODE_AUTO

        await self._send_ir()
        self.async_write_ha_state()

    async def async_set_fan_mode(self, fan_mode: str) -> None:
        """Set fan mode.

        :param fan_mode: The desired fan speed string.
        """
        self._attr_fan_mode = fan_mode
        self._data.ir_state.fan = FAN_MODE_TO_IR.get(fan_mode, IR_FAN_AUTO)
        await self._send_ir()
        self.async_write_ha_state()

    async def async_set_swing_mode(self, swing_mode: str) -> None:
        """Set swing mode.

        :param swing_mode: The desired swing mode string.
        """
        self._attr_swing_mode = swing_mode
        self._data.ir_state.swing = SWING_MODE_TO_IR.get(swing_mode, IR_SWING_OFF)
        await self._send_ir()
        self.async_write_ha_state()

    # =========================================================================
    # IR Transmission
    # =========================================================================

    async def _send_ir(self) -> None:
        """Build the IR command from current state and send via the configured transport."""
        self._data.ir_state.temperature = self._attr_target_temperature
        await async_send_ir_command(self.hass, self._data)

    # =========================================================================
    # Timer Services
    # =========================================================================

    @staticmethod
    def _resolve_minutes(
        minutes: int | None, time_val: datetime.time | None
    ) -> int:
        """Resolve a timer duration from *minutes* or *time* (time of day).

        If *time* is given, the offset from "now" is computed.  If the
        resulting time is in the past, it wraps to the next day.

        :param minutes: Explicit duration in minutes (1–720).
        :param time_val: Target wall-clock time (HH:MM).
        :return: Duration in minutes.
        :raises ValueError: If neither or both parameters are given, or if
            the computed duration exceeds the 12-hour maximum.
        """
        if minutes is not None and time_val is not None:
            raise ValueError("Specify 'minutes' or 'time', not both")
        if minutes is not None:
            return minutes
        if time_val is None:
            raise ValueError("Either 'minutes' or 'time' must be provided")

        now = dt_util.now()
        target = now.replace(
            hour=time_val.hour,
            minute=time_val.minute,
            second=0,
            microsecond=0,
        )
        if target <= now:
            target += datetime.timedelta(days=1)
        delta_mins = int((target - now).total_seconds() / 60)
        if delta_mins > TIMER_MAX:
            raise ValueError(
                f"Target time is {delta_mins} minutes away; "
                f"maximum is {TIMER_MAX} minutes (12 hours)"
            )
        return max(1, delta_mins)

    async def async_set_off_timer(
        self,
        minutes: int | None = None,
        time: datetime.time | None = None,  # noqa: A002 — name required by HA service schema
    ) -> None:
        """Set an off timer — turn the AC off after the specified duration.

        :param minutes: Duration in minutes (1–720).
        :param time: Wall-clock time to turn off (HH:MM).  Offset from
            now is computed automatically.
        """
        mins = self._resolve_minutes(minutes, time)
        _LOGGER.debug("Setting off timer: %d minutes", mins)
        ir_bytes = FujitsuACCodec.build_off_timer(self._data.ir_state, mins)
        await async_send_ir_bytes(
            self.hass, self._data.transport, ir_bytes
        )

    async def async_set_on_timer(
        self,
        minutes: int | None = None,
        time: datetime.time | None = None,  # noqa: A002 — name required by HA service schema
        mode: str | None = None,
        temperature: float | None = None,
        fan_mode: str | None = None,
        swing_mode: str | None = None,
    ) -> None:
        """Set an on timer — turn the AC on after the specified duration.

        Optionally overrides the mode, temperature, fan, and swing for
        the state the AC should use when the timer fires.

        :param minutes: Duration in minutes (1–720).
        :param time: Wall-clock time to turn on (HH:MM).
        :param mode: HVAC mode string (auto, cool, heat, dry, fan_only).
        :param temperature: Target temperature in °C.
        :param fan_mode: Fan speed string.
        :param swing_mode: Swing mode string.
        """
        mins = self._resolve_minutes(minutes, time)

        # Start from current state, apply any overrides
        ir_state = self._data.ir_state
        if mode is not None:
            hvac = HVACMode(mode)
            ir_state.mode = HVAC_MODE_TO_IR.get(hvac, ir_state.mode)
        if temperature is not None:
            ir_state.temperature = round(
                max(MIN_TEMP, min(MAX_TEMP, temperature)), 1
            )
        if fan_mode is not None:
            ir_state.fan = FAN_MODE_TO_IR.get(fan_mode, ir_state.fan)
        if swing_mode is not None:
            ir_state.swing = SWING_MODE_TO_IR.get(swing_mode, ir_state.swing)

        _LOGGER.debug("Setting on timer: %d minutes", mins)
        ir_bytes = FujitsuACCodec.build_on_timer(ir_state, mins)
        await async_send_ir_bytes(
            self.hass, self._data.transport, ir_bytes
        )

    async def async_set_sleep_timer(
        self,
        minutes: int | None = None,
        time: datetime.time | None = None,  # noqa: A002 — name required by HA service schema
    ) -> None:
        """Set a sleep timer — AC turns off with gradual comfort adjustment.

        :param minutes: Duration in minutes (1–720).
        :param time: Wall-clock time to sleep-off (HH:MM).
        """
        mins = self._resolve_minutes(minutes, time)
        _LOGGER.debug("Setting sleep timer: %d minutes", mins)
        ir_bytes = FujitsuACCodec.build_sleep_timer(self._data.ir_state, mins)
        await async_send_ir_bytes(
            self.hass, self._data.transport, ir_bytes
        )

    async def async_cancel_timer(self) -> None:
        """Cancel any active timer."""
        _LOGGER.debug("Cancelling timer")
        ir_bytes = FujitsuACCodec.build_cancel_timer(self._data.ir_state)
        await async_send_ir_bytes(
            self.hass, self._data.transport, ir_bytes
        )
