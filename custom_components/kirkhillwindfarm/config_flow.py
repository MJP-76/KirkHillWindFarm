"""Config flow for Kirk Hill Wind Farm integration."""

from homeassistant import config_entries
from homeassistant.core import HomeAssistant

from .const import DOMAIN


class KirkHillConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Config flow for Kirk Hill Wind Farm."""

    VERSION = 1

    async def async_step_user(self, user_input=None):
        """Handle a flow initialized by the user."""
        if user_input is not None:
            return self.async_create_entry(
                title="Kirk Hill Wind Farm",
                data=user_input,
            )

        return self.async_show_form(
            step_id="user",
            data_schema=None,
        )
