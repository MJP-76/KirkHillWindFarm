"""Sensor platform for Kirk Hill Wind Farm."""
import logging
from datetime import timedelta
import aiohttp
import async_timeout

from homeassistant.components.sensor import (
    SensorEntity,
    SensorDeviceClass,
    SensorStateClass,
)
from homeassistant.const import CONF_API_KEY, UnitOfPower
from homeassistant.helpers.entity import Entity

_LOGGER = logging.getLogger(__name__)

# Refresh data every 5 minutes
SCAN_INTERVAL = timedelta(minutes=5)
URL = "https://kirkhillcoop.org"

async def async_setup_platform(hass, config, async_add_entities, discovery_info=None):
    """Set up the Kirk Hill sensors."""
    api_key = hass.data["kirkhill_wind"][CONF_API_KEY]
    
    # We add two sensors: one for your personal share, one for the whole site
    async_add_entities([
        KirkHillSensor(api_key, "Your Share", scope="user"),
        KirkHillSensor(api_key, "Whole Site", scope="site")
    ], True)

class KirkHillSensor(SensorEntity):
    """Representation of a Kirk Hill Wind Farm generation sensor."""

    def __init__(self, api_key, name_suffix, scope):
        """Initialize the sensor."""
        self._api_key = api_key
        self._scope = scope
        self._attr_name = f"Kirk Hill Wind {name_suffix}"
        self._attr_unique_id = f"kirkhill_wind_{scope}"
        self._attr_native_unit_of_measurement = UnitOfPower.KILOWATT
        self._attr_device_class = SensorDeviceClass.POWER
        self._attr_state_class = SensorStateClass.MEASUREMENT
        self._attr_native_value = None

    async def async_update(self):
        """Fetch latest live data from the Kirk Hill Wind Farm API."""
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Accept": "application/json"
        }
        params = {"scope": self._scope}

        try:
            async with aiohttp.ClientSession() as session:
                with async_timeout.timeout(10):
                    async with session.get(URL, headers=headers, params=params) as response:
                        if response.status == 200:
                            data = await response.json()
                            # Adjust "power" key based on the exact JSON payload schema 
                            # returned by dashboard.kirkhillcoop.org/api-docs
                            self._attr_native_value = data.get("power", 0)
                        elif response.status == 401:
                            _LOGGER.error("Invalid API Key for Kirk Hill Wind Farm API")
                        else:
                            _LOGGER.error("Error fetching Kirk Hill data: %s", response.status)
        except Exception as err:
            _LOGGER.error("Failed to connect to Kirk Hill API: %s", err)
