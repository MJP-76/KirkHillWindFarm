from homeassistant import config_entries
import voluptuous as vol

DOMAIN = "kirkhill_wind"


class KirkHillConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Config flow for Kirk Hill Wind Farm."""

    VERSION = 1

    async def async_step_user(self, user_input=None):
        errors = {}

        if user_input is not None:
            return self.async_create_entry(
                title="Kirk Hill Wind Farm",
                data=user_input,
            )

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema({
                vol.Required("base_url"): str,
                vol.Required("api_key"): str,
            }),
            errors=errors,
        )
