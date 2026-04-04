"""Config flow for Fujitsu AC IR integration."""

from __future__ import annotations

from typing import Any

import voluptuous as vol

from homeassistant.config_entries import ConfigFlow, ConfigFlowResult
from homeassistant.helpers.selector import (
    EntitySelector,
    EntitySelectorConfig,
    TextSelector,
)

from .const import CONF_BROADLINK_DEVICE, CONF_NAME, DEFAULT_NAME, DOMAIN


class FujitsuACIRConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Fujitsu AC IR."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle the initial step.

        :param user_input: Form data submitted by the user, or ``None`` on
            first display.
        :return: A config flow result (form or entry creation).
        """
        errors: dict[str, str] = {}

        if user_input is not None:
            # Validate the broadlink remote entity exists
            broadlink_entity = user_input[CONF_BROADLINK_DEVICE]
            state = self.hass.states.get(broadlink_entity)
            if state is None:
                errors[CONF_BROADLINK_DEVICE] = "entity_not_found"
            else:
                await self.async_set_unique_id(
                    f"fujitsu_ac_ir_{broadlink_entity}"
                )
                self._abort_if_unique_id_configured()

                return self.async_create_entry(
                    title=user_input.get(CONF_NAME, DEFAULT_NAME),
                    data=user_input,
                )

        data_schema = vol.Schema(
            {
                vol.Required(CONF_NAME, default=DEFAULT_NAME): TextSelector(),
                vol.Required(CONF_BROADLINK_DEVICE): EntitySelector(
                    EntitySelectorConfig(domain="remote")
                ),
            }
        )

        return self.async_show_form(
            step_id="user",
            data_schema=data_schema,
            errors=errors,
        )
