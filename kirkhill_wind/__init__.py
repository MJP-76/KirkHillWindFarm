"""The Kirk Hill Wind Farm Integration."""
import logging
import voluptuous as vol
import homeassistant.helpers.config_validation as cv
from homeassistant.const import CONF_API_KEY
from homeassistant.core import HomeAssistant
from homeassistant.helpers.typing import ConfigType

_LOGGER = logging.getLogger(__name__)

DOMAIN = "kirkhill_wind"

CONFIG_SCHEMA = vol.Schema(
    {
        DOMAIN: vol.Schema(
            {
                vol.Required(CONF_API_KEY): cv.string,
            }
        )
    },
    extra=vol.ALLOW_EXTRA,
)

async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Set up the Kirk Hill component from YAML config."""
    if DOMAIN not in config:
        return True

    hass.data[DOMAIN] = {
        CONF_API_KEY: config[DOMAIN][CONF_API_KEY]
    }

    # Forward the setup to the sensor platform
    hass.async_create_task(
        hass.helpers.discovery.async_load_platform("sensor", DOMAIN, {}, config)
    )

    return True
