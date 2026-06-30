from datetime import timedelta
import logging
import async_timeout
import aiohttp

from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession

_LOGGER = logging.getLogger(__name__)

# Base API URL matching the documentation endpoint schema
BASE_URL = "https://dashboard.kirkhillcoop.org/api/v1"

class KirkHillCoordinator(DataUpdateCoordinator):
    """Class to manage fetching live Kirk Hill Wind Farm API data."""

    def __init__(self, hass: HomeAssistant, api_key: str) -> None:
        """Initialize the coordinator."""
        self.api_key = api_key
        self.session = async_get_clientsession(hass)
        
        # Poll every 5 minutes to avoid overwhelming the read-only API
        super().__init__(
            hass,
            _LOGGER,
            name="Kirk Hill Wind Farm",
            update_interval=timedelta(minutes=5),
        )

    async def _async_update_data(self) -> dict:
        """Fetch and parse live data from the Kirk Hill Wind Farm API."""
        # Setup headers using the Authorize API Key specification
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Accept": "application/json",
        }
        
        # Change scope to 'site' if you want whole wind farm values instead of member share values
        url = f"{BASE_URL}/generation?scope=member"

        try:
            async with async_timeout.timeout(15):
                response = await self.session.get(url, headers=headers)
                
                if response.status == 401:
                    raise UpdateFailed("Invalid API Key. Please verify your Kirk Hill Dashboard API credentials.")
                elif response.status != 200:
                    raise UpdateFailed(f"API returned an unhealthy error code: {response.status}")

                data = await response.json()
                
                # Check for an empty or faulty structure
                if not data:
                    raise UpdateFailed("API returned an empty payload.")

                # Extract parameters safely based on common cooperative API metrics.
                # Adjust these exact keys to match the JSON response structure of your /generation endpoint.
                return {
                    "current_generation": float(data.get("current_power_w", 0)),
                    "total_generated": float(data.get("total_energy_kwh", 0)),
                    "capacity_factor": float(data.get("capacity_factor_percent", 0)),
                }

        except aiohttp.ClientError as err:
            raise UpdateFailed(f"Network error communicating with Kirk Hill API: {err}")
        except Exception as err:
            raise UpdateFailed(f"Unexpected error parsing Kirk Hill wind data: {err}")
