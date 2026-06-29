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
from homeassistant.helpers.aiohttp_client import async_get_clientsession

_LOGGER = logging.getLogger(__name__)
SCAN_INTERVAL = timedelta(minutes=5)
URL = "https://kirkhillcoop.org"

async def async_setup_entry(hass, entry, async_add_entities):
    """Set up the Kirk Hill sensors via UI configuration entry."""
    config = hass.data["kirkhill_wind"][entry.entry_id]
    api_key = config[CONF_API_KEY]
    session = async_get_clientsession(hass)
    
    async_add_entities([
        KirkHillSensor(session, api_key, "Your Share", scope="user"),
        KirkHillSensor(session, api_key, "Whole Site", scope="site")
    ], True)

class KirkHillSensor(SensorEntity):
    """Representation of a Kirk Hill Wind Farm generation sensor."""

    def __init__(self, session, api_key, name_suffix, scope):
        """Initialize the sensor."""
        self._session = session
        self._api_key = api_key
        self._scope = scope
        self._attr_name = f"Kirk Hill Wind {name_suffix}"
        self._attr_unique_id = f"kirkhill_wind_{scope}_{api_key[:6]}"
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
            async with async_timeout.timeout(10):
                async with self._session.get(URL, headers=headers, params=params) as response:
                    if response.status == 200:
                        data = await response.json()
                        self._attr_native_value = data.get("power", 0)
                    elif response.status == 401:
                        _LOGGER.error("Invalid API Key for Kirk Hill Wind Farm API")
                    else:
                        _LOGGER.error("Error fetching Kirk Hill data: %s", response.status)
        except Exception as err:
            _LOGGER.error("Failed to connect to Kirk Hill API: %s", err)
