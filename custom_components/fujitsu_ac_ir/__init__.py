"""Fujitsu AC IR integration for Home Assistant.

Controls a Fujitsu air conditioner via an IR blaster by assembling
full AC state IR commands using the decoded Fujitsu protocol
(AR-RWE3E / ARREW4E family).

The integration is transport-agnostic — the IR blaster backend
(Broadlink, ESPHome, etc.) is selected during configuration and
handled by :mod:`ir_transport`.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant

from .const import CONF_BROADLINK_DEVICE, CONF_TRANSPORT_TYPE, DOMAIN
from .ir_codec import FujitsuACCodec, FujitsuACState
from .ir_transport import (
    TRANSPORT_BROADLINK,
    IRTransport,
    create_transport,
)

_LOGGER = logging.getLogger(__name__)

PLATFORMS = [Platform.CLIMATE, Platform.SWITCH]


@dataclass
class FujitsuACIRData:
    """Shared runtime data for a Fujitsu AC IR config entry.

    Both the climate and switch entities reference the same instance so
    that every IR command carries the complete, up-to-date AC state.

    :param ir_state: Current desired AC state.
    :param transport: IR blaster transport backend.
    """

    ir_state: FujitsuACState
    transport: IRTransport


async def async_send_ir_command(
    hass: HomeAssistant,
    data: FujitsuACIRData,
) -> None:
    """Build and send the IR command for the current AC state.

    :param hass: Home Assistant instance.
    :param data: Shared integration runtime data.
    """
    ir_bytes = FujitsuACCodec.build_command(data.ir_state)
    timings = FujitsuACCodec.bytes_to_timings(ir_bytes)

    _LOGGER.debug(
        "Sending Fujitsu AC IR: power=%s mode=%s temp=%.1f fan=%s swing=%s quiet=%s",
        data.ir_state.power,
        data.ir_state.mode,
        data.ir_state.temperature,
        data.ir_state.fan,
        data.ir_state.swing,
        data.ir_state.outside_quiet,
    )

    await data.transport.async_send_timings(timings)


async def async_send_ir_bytes(
    hass: HomeAssistant,
    transport: IRTransport,
    ir_bytes: bytes,
) -> None:
    """Send pre-built protocol bytes via the configured transport.

    :param hass: Home Assistant instance.
    :param transport: IR blaster transport backend.
    :param ir_bytes: Raw Fujitsu AC protocol bytes.
    """
    timings = FujitsuACCodec.bytes_to_timings(ir_bytes)
    await transport.async_send_timings(timings)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Fujitsu AC IR from a config entry.

    :param hass: Home Assistant instance.
    :param entry: Config entry being set up.
    :return: ``True`` if setup succeeded.
    """
    hass.data.setdefault(DOMAIN, {})

    # Determine transport type — default to Broadlink for backward
    # compatibility with config entries created before the transport
    # selection was added.
    transport_type = entry.data.get(CONF_TRANSPORT_TYPE, TRANSPORT_BROADLINK)
    blaster_entity = entry.data[CONF_BROADLINK_DEVICE]
    transport = create_transport(transport_type, hass, blaster_entity)

    hass.data[DOMAIN][entry.entry_id] = FujitsuACIRData(
        ir_state=FujitsuACState(),
        transport=transport,
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
