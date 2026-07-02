"""Config flow for Kirk Hill Wind Farm integration."""
from __future__ import annotations

from typing import Any
import voluptuous as vol

from homeassistant import config_entries
from homeassistant.data_entry_flow import FlowResult

from .const import DOMAIN, DEFAULT_NAME, CONF_API_KEY

class KirkhillCoopConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Kirk Hill Wind Farm."""

    # Incremented to version 2 to bypass Home Assistant's local UI cache
    VERSION = 2

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle the step where the user enters their credentials."""
        # 1. Prevent users from creating duplicate instances of this integration
        if self._async_current_entries():
            return self.async_abort(reason="single_instance_allowed")

        # 2. Process input once the user clicks submit
        if user_input is not None:
            return self.async_create_entry(
                title=DEFAULT_NAME, 
                data={CONF_API_KEY: user_input[CONF_API_KEY]}
            )

        # 3. Render the form text entry box safely on modern HA versions
        return self.async_show_form(
            step_id="user", 
            data_schema=vol.Schema({
                vol.Required(CONF_API_KEY): str,
            })
        )
