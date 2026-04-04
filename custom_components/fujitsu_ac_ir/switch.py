"""Fujitsu AC IR switch platform.

Provides a Home Assistant Switch entity that controls the outside-unit
quiet mode on a Fujitsu air conditioner via a Broadlink IR blaster.

When enabled, the outdoor unit runs at reduced noise levels.  The flag
is encoded in byte 14, bit 7 of the 16-byte Fujitsu IR protocol message.
Toggling the switch while the AC is off updates the stored state so the
flag will be included in the next power-on command.
"""

from __future__ import annotations

from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import FujitsuACIRData, async_send_ir_command
from .const import CONF_NAME, DEFAULT_NAME, DOMAIN


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the Fujitsu AC IR switch entity from a config entry.

    :param hass: Home Assistant instance.
    :param config_entry: Config entry being set up.
    :param async_add_entities: Callback to register new entities.
    """
    name = config_entry.data.get(CONF_NAME, DEFAULT_NAME)
    data: FujitsuACIRData = hass.data[DOMAIN][config_entry.entry_id]

    async_add_entities(
        [FujitsuACOutsideQuietSwitch(config_entry.entry_id, name, data)],
        update_before_add=False,
    )


class FujitsuACOutsideQuietSwitch(SwitchEntity):
    """Switch entity for the Fujitsu AC outside-unit quiet mode.

    :param entry_id: Config entry unique ID.
    :param name: Display name prefix (the configured AC name).
    :param data: Shared integration runtime data.
    """

    _attr_has_entity_name = True

    def __init__(
        self,
        entry_id: str,
        name: str,
        data: FujitsuACIRData,
    ) -> None:
        """Initialize the switch entity.

        :param entry_id: Config entry unique ID.
        :param name: Display name prefix (the configured AC name).
        :param data: Shared integration runtime data.
        """
        self._data = data
        self._attr_unique_id = f"fujitsu_ac_ir_{entry_id}_outside_quiet"
        self._attr_name = f"{name} Outside Quiet"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry_id)},
            name=name,
            manufacturer="Fujitsu",
            model="AR-RWE3E / ARREW4E",
            sw_version="0.1.1",
        )

    @property
    def icon(self) -> str:
        """Return the icon based on the current state.

        :return: MDI icon string.
        """
        return "mdi:volume-off" if self.is_on else "mdi:volume-vibrate"

    @property
    def is_on(self) -> bool:
        """Return whether outside-unit quiet mode is active.

        :return: ``True`` when quiet mode is enabled.
        """
        return self._data.ir_state.outside_quiet

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Enable outside-unit quiet mode.

        If the AC is currently on, a full state IR command is sent
        immediately.  Otherwise the flag is stored and will be included
        in the next power-on command.

        :param kwargs: Additional arguments (unused).
        """
        self._data.ir_state.outside_quiet = True
        if self._data.ir_state.power:
            await async_send_ir_command(self.hass, self._data)
        self.async_write_ha_state()

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Disable outside-unit quiet mode.

        If the AC is currently on, a full state IR command is sent
        immediately.  Otherwise the flag is stored and will be included
        in the next power-on command.

        :param kwargs: Additional arguments (unused).
        """
        self._data.ir_state.outside_quiet = False
        if self._data.ir_state.power:
            await async_send_ir_command(self.hass, self._data)
        self.async_write_ha_state()
