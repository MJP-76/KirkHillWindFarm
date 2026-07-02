import voluptuous as vol

from homeassistant import config_entries

from .const import DOMAIN


class KirkHillConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1

    async def async_step_user(self, user_input=None):
        if user_input is not None:
            return self.async_create_entry(
                title="Kirk Hill Wind Farm",
                data={
                    "api_key": user_input["api_key"],
                },
            )

        schema = vol.Schema(
            {
                vol.Required("api_key"): str,
            }
        )

        return self.async_show_form(
            step_id="user",
            data_schema=schema,
        )
