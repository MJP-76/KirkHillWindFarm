"""Platform for sensor integration."""
import logging
from datetime import timedelta
import aiohttp
import async_timeout

from homeassistant.components.sensor import SensorEntity
from homeassistant.helpers.aiohttp_client import async_get_clientsession

DOMAIN = "kirkhill_wind"
# Update this to your precise Kirk Hill dashboard endpoint
API_URL = "https://dashboard.kirkhillcoop.org/api-docs" 

SCAN_INTERVAL = timedelta(minutes=5) # Fetch data every 5 minutes
_LOGGER = logging.getLogger(__name__)

async def async_setup_entry(hass, config_entry, async_add_entities):
    """Set up the Kirk Hill sensor platform from a config entry."""
    api_key = config_entry.data.get("api_key")
    session = async_get_clientsession(hass)
    
    # Add your sensors to Home Assistant
    async_add_entities([KirkHillGenerationSensor(session, api_key)], True)


class KirkHillGenerationSensor(SensorEntity):
    """Representation of a Kirk Hill Wind Farm Power Generation Sensor."""

    def __init__(self, session, api_key):
        """Initialize the sensor."""
        self._session = session
        self._api_key = api_key
        self._state = None
        self._attrs = {}
        self._available = False

    @property
    def name(self):
        """Return the name of the sensor."""
        return "Kirk Hill Power Generation"

    @property
    def unique_id(self):
        """Return a unique ID to manage this entity in the UI."""
        return f"kirkhill_wind_generation_{self._api_key[:6]}"

    @property
    def state(self):
        """Return the current power generation state."""
        return self._state

    @property
    def unit_of_measurement(self):
        """Return the unit of measurement."""
        return "kW"  # or kWh depending on what the API spits out

    @property
    def available(self):
        """Return True if entity is available."""
        return self._available

    @property
    def extra_state_attributes(self):
        """Return device specific state attributes."""
        return self._attrs

    async def async_update(self):
        """Fetch new state data from the Kirk Hill API."""
        headers = {"Authorization": f"Bearer {self._api_key}"}
        
        try:
            with async_timeout.timeout(10):
                response = await self._session.get(API_URL, headers=headers)
                
            if response.status == 200:
                data = await response.json()
                # Parse data out of your specific API JSON response structure
                self._state = data.get("generation", 0) 
                self._attrs = {"updated_at": data.get("timestamp")}
                self._available = True
            else:
                _LOGGER.error("Error fetching data from Kirk Hill API: %s", response.status)
                self._available = False
                
        except Exception as err:
            _LOGGER.error("Failed to connect to Kirk Hill API: %s", err)
            self._available = False
