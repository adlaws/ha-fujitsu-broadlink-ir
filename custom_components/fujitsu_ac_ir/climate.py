"""Fujitsu AC IR climate platform.

Provides a Home Assistant Climate entity that controls a Fujitsu air conditioner
via a Broadlink IR blaster. Commands are assembled from the decoded Fujitsu IR
protocol (AR-RWE3E / ARREW4E family, protocol 0x31).

Each command sent encodes the FULL desired AC state (mode, temp, fan, swing),
not just the changed setting — matching how the physical remote works.
"""

from __future__ import annotations

from typing import Any

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
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import FujitsuACIRData, async_send_ir_command
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
)

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


class FujitsuACClimate(ClimateEntity):
    """Climate entity for Fujitsu AC controlled via Broadlink IR blaster."""

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
        """Build the IR command from current state and send via Broadlink."""
        self._data.ir_state.temperature = self._attr_target_temperature
        await async_send_ir_command(self.hass, self._data)
