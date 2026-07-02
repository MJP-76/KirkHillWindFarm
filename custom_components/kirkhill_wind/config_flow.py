from homeassistant import config_entries
import voluptuous as vol

from .api import KirkHillApi


class ConfigFlow(config_entries.ConfigFlow, domain="kirkhill"):
    VERSION = 1

    async def async_step_user(self, user_input=None):
        errors = {}

        if user_input is not None:
            api = KirkHillApi(
                user_input["base_url"],
                user_input["api_key"],
            )

            session = self.hass.helpers.aiohttp_client.async_get_clientsession(self.hass)

            try:
                await api.test(session)
            except Exception:
                errors["base"] = "cannot_connect"
            else:
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
