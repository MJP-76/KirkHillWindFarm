import voluptuous as vol
from homeassistant import config_entries

from .const import ( DOMAIN )

class RippleEnergyConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    async def async_step_user(self, user_input=None):
        errors = {}
        if user_input is None:
            return self._show_setup_form()

        errors = {}

        # Validate the API key length
        if len(user_input['api_key']) < 60:
            errors['base'] = 'invalid_api_key_length'

        if not errors:
            return self.async_create_entry(title="Ripple Energy", data=user_input)
        
        return self._show_setup_form(errors)

    def _show_setup_form(self, errors=None):
        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Required("api_key"): str
                }
            ),
            errors=errors or {},
        )