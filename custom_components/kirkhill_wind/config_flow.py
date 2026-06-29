"""Config flow for Kirk Hill Wind Farm integration."""
import logging
import aiohttp
import async_timeout
import voluptuous as vol

from homeassistant import config_entries
from homeassistant.const import CONF_API_KEY
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession

_LOGGER = logging.getLogger(__name__)
DOMAIN = "kirkhill_wind"
URL = "https://kirkhillcoop.org"

async def validate_input(hass: HomeAssistant, data: dict) -> dict:
    """Validate the user input allows us to connect to Kirk Hill API."""
    session = async_get_clientsession(hass)
    headers = {
        "Authorization": f"Bearer {data[CONF_API_KEY]}",
        "Accept": "application/json"
    }
    
    try:
        async with async_timeout.timeout(10):
            async with session.get(URL, headers=headers, params={"scope": "site"}) as response:
                if response.status == 401:
                    raise InvalidAuth
                if response.status != 200:
                    raise CannotConnect
    except (aiohttp.ClientError, asyncio.TimeoutError):
        raise CannotConnect

    # Return the title info for the integration block in UI
    return {"title": "Kirk Hill Wind Farm"}

class KirkHillConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Kirk Hill Wind Farm."""

    VERSION = 1

    async def async_step_user(self, user_input=None):
        """Handle the initial user interaction setup step."""
        errors = {}
        if user_input is not None:
            try:
                info = await validate_input(self.hass, user_input)
                
                # Prevent configuring the same API token twice
                await self.async_set_unique_id(user_input[CONF_API_KEY])
                self._abort_if_unique_id_configured()

                return self.async_create_entry(title=info["title"], data=user_input)
            except InvalidAuth:
                errors["base"] = "invalid_auth"
            except CannotConnect:
                errors["base"] = "cannot_connect"
            except Exception:  # pylint: disable=broad-except
                _LOGGER.exception("Unexpected exception")
                errors["base"] = "unknown"

        # Schema defining the text field form for the user interface
        DATA_SCHEMA = vol.Schema({
            vol.Required(CONF_API_KEY): str,
        })

        return self.async_show_form(
            step_id="user", data_schema=DATA_SCHEMA, errors=errors
        )

class CannotConnect(Exception):
    """Error to indicate we cannot connect."""

class InvalidAuth(Exception):
    """Error to indicate there is invalid auth."""
