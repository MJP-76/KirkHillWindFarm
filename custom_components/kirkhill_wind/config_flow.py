"""Config flow for Kirk Hill Wind Farm integration."""
import logging
import voluptuous as vol
from homeassistant import config_entries
from homeassistant.core import callback

DOMAIN = "kirkhill_wind"

_LOGGER = logging.getLogger(__name__)

class KirkHillConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Kirk Hill Wind Farm."""

    VERSION = 1

    async def async_step_user(self, user_input=None):
        """Handle the initial step where the user inputs their API key."""
        errors = {}

        if user_input is not None:
            # Here you can optionally add an API validation check later
            api_key = user_input["api_key"]
            
            # Save the entry and complete the setup UI
            return self.async_create_entry(
                title="Kirk Hill Wind Farm", 
                data={"api_key": api_key}
            )

        # Build the form schema for the UI
        data_schema = vol.Schema({
            vol.Required("api_key"): str,
        })

        return self.async_show_form(
            step_id="user", 
            data_schema=data_schema, 
            errors=errors
        )
