"""Fujitsu AC IR integration for Home Assistant.

Controls a Fujitsu air conditioner via a Broadlink IR blaster by
assembling full AC state IR commands using the decoded Fujitsu protocol
(AR-RWE3E / ARREW4E family).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant

from .const import CONF_BROADLINK_DEVICE, DOMAIN
from .ir_codec import FujitsuACCodec, FujitsuACState

_LOGGER = logging.getLogger(__name__)

PLATFORMS = [Platform.CLIMATE, Platform.SWITCH]


@dataclass
class FujitsuACIRData:
    """Shared runtime data for a Fujitsu AC IR config entry.

    Both the climate and switch entities reference the same instance so
    that every IR command carries the complete, up-to-date AC state.

    :param ir_state: Current desired AC state.
    :param broadlink_entity: Entity ID of the Broadlink remote.
    """

    ir_state: FujitsuACState
    broadlink_entity: str


async def async_send_ir_command(
    hass: HomeAssistant,
    data: FujitsuACIRData,
) -> None:
    """Build and send the IR command for the current AC state.

    :param hass: Home Assistant instance.
    :param data: Shared integration runtime data.
    """
    broadlink_code = FujitsuACCodec.build_command(data.ir_state)

    _LOGGER.debug(
        "Sending Fujitsu AC IR: power=%s mode=%s temp=%.1f fan=%s swing=%s quiet=%s",
        data.ir_state.power,
        data.ir_state.mode,
        data.ir_state.temperature,
        data.ir_state.fan,
        data.ir_state.swing,
        data.ir_state.outside_quiet,
    )

    await _send_broadlink_code(hass, data.broadlink_entity, broadlink_code)


async def async_send_ir_code(
    hass: HomeAssistant,
    broadlink_entity: str,
    broadlink_code: str,
) -> None:
    """Send a pre-built Broadlink base64 IR code.

    :param hass: Home Assistant instance.
    :param broadlink_entity: Entity ID of the Broadlink remote.
    :param broadlink_code: Base64-encoded Broadlink IR code.
    """
    await _send_broadlink_code(hass, broadlink_entity, broadlink_code)


async def _send_broadlink_code(
    hass: HomeAssistant,
    broadlink_entity: str,
    broadlink_code: str,
) -> None:
    """Send a Broadlink base64 IR code via the remote.send_command service.

    :param hass: Home Assistant instance.
    :param broadlink_entity: Entity ID of the Broadlink remote.
    :param broadlink_code: Base64-encoded Broadlink IR code.
    """
    try:
        await hass.services.async_call(
            "remote",
            "send_command",
            {
                "entity_id": broadlink_entity,
                "command": f"b64:{broadlink_code}",
            },
            blocking=True,
        )
    except Exception:  # noqa: BLE001  # IR send failures are non-fatal
        _LOGGER.exception(
            "Failed to send IR command via %s", broadlink_entity
        )


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Fujitsu AC IR from a config entry.

    :param hass: Home Assistant instance.
    :param entry: Config entry being set up.
    :return: ``True`` if setup succeeded.
    """
    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN][entry.entry_id] = FujitsuACIRData(
        ir_state=FujitsuACState(),
        broadlink_entity=entry.data[CONF_BROADLINK_DEVICE],
    )

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry.

    :param hass: Home Assistant instance.
    :param entry: Config entry being unloaded.
    :return: ``True`` if unload succeeded.
    """
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id, None)
        if not hass.data[DOMAIN]:
            hass.data.pop(DOMAIN, None)
    return unload_ok
