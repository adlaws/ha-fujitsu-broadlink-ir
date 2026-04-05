"""Config flow for Fujitsu AC IR integration."""

from __future__ import annotations

from typing import Any

import voluptuous as vol

from homeassistant.config_entries import ConfigFlow, ConfigFlowResult
from homeassistant.helpers.selector import (
    EntitySelector,
    EntitySelectorConfig,
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
    TextSelector,
)

from .const import (
    CONF_BROADLINK_DEVICE,
    CONF_NAME,
    CONF_TRANSPORT_TYPE,
    DEFAULT_NAME,
    DOMAIN,
)
from .ir_transport import (
    ENTITY_TRANSPORTS,
    TRANSPORT_BROADLINK,
    TRANSPORT_REGISTRY,
)


# Map transport key → human-readable label
_TRANSPORT_OPTIONS = [
    {"value": key, "label": key.title()}
    for key in TRANSPORT_REGISTRY
]


class FujitsuACIRConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Fujitsu AC IR."""

    VERSION = 1

    def __init__(self) -> None:
        """Initialise the config flow."""
        self._user_data: dict[str, Any] = {}

    # ----- Step 1: name + transport type ------------------------------------

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Step 1 — choose a name and IR blaster type.

        :param user_input: Form data submitted by the user, or ``None``
            on first display.
        :return: A config flow result (form or next step).
        """
        if user_input is not None:
            self._user_data = user_input
            transport = user_input[CONF_TRANSPORT_TYPE]
            if transport in ENTITY_TRANSPORTS:
                return await self.async_step_blaster()
            return await self.async_step_esphome()

        data_schema = vol.Schema(
            {
                vol.Required(CONF_NAME, default=DEFAULT_NAME): TextSelector(),
                vol.Required(
                    CONF_TRANSPORT_TYPE, default=TRANSPORT_BROADLINK
                ): SelectSelector(
                    SelectSelectorConfig(
                        options=_TRANSPORT_OPTIONS,
                        mode=SelectSelectorMode.DROPDOWN,
                    )
                ),
            }
        )

        return self.async_show_form(
            step_id="user",
            data_schema=data_schema,
        )

    # ----- Step 2a: entity selector (Broadlink / SwitchBot / Aqara) ---------

    async def async_step_blaster(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Step 2a — select the remote entity for the IR blaster.

        :param user_input: Form data submitted by the user, or ``None``
            on first display.
        :return: A config flow result (form or entry creation).
        """
        errors: dict[str, str] = {}

        if user_input is not None:
            blaster_entity = user_input[CONF_BROADLINK_DEVICE]
            state = self.hass.states.get(blaster_entity)
            if state is None:
                errors[CONF_BROADLINK_DEVICE] = "entity_not_found"
            else:
                data = {**self._user_data, **user_input}
                await self.async_set_unique_id(
                    f"fujitsu_ac_ir_{blaster_entity}"
                )
                self._abort_if_unique_id_configured()
                return self.async_create_entry(
                    title=data.get(CONF_NAME, DEFAULT_NAME),
                    data=data,
                )

        data_schema = vol.Schema(
            {
                vol.Required(CONF_BROADLINK_DEVICE): EntitySelector(
                    EntitySelectorConfig(domain="remote")
                ),
            }
        )

        return self.async_show_form(
            step_id="blaster",
            data_schema=data_schema,
            errors=errors,
        )

    # ----- Step 2b: ESPHome device name -------------------------------------

    async def async_step_esphome(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Step 2b — enter the ESPHome device node name.

        :param user_input: Form data submitted by the user, or ``None``
            on first display.
        :return: A config flow result (form or entry creation).
        """
        errors: dict[str, str] = {}

        if user_input is not None:
            device_name = user_input[CONF_BROADLINK_DEVICE].strip()
            if not device_name:
                errors[CONF_BROADLINK_DEVICE] = "invalid_device_name"
            else:
                data = {**self._user_data, CONF_BROADLINK_DEVICE: device_name}
                await self.async_set_unique_id(
                    f"fujitsu_ac_ir_esphome_{device_name}"
                )
                self._abort_if_unique_id_configured()
                return self.async_create_entry(
                    title=data.get(CONF_NAME, DEFAULT_NAME),
                    data=data,
                )

        data_schema = vol.Schema(
            {
                vol.Required(CONF_BROADLINK_DEVICE): TextSelector(),
            }
        )

        return self.async_show_form(
            step_id="esphome",
            data_schema=data_schema,
            errors=errors,
        )
