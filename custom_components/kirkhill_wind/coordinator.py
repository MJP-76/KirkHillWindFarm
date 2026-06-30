from datetime import timedelta
import logging
import async_timeout
import aiohttp

from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession

_LOGGER = logging.getLogger(__name__)

# This is the web address for the Kirk Hill API
BASE_URL = "https://kirkhillcoop.org"

class KirkHillCoordinator(DataUpdateCoordinator):
    """Class to manage fetching live Kirk Hill Wind Farm API data."""

    def __init__(self, hass: HomeAssistant, api_key: str) -> None:
        """Initialize the coordinator."""
        self.api_key = api_key
        self.session = async_get_clientsession(hass)
        
        # This tells Home Assistant to check the API for new data every 5 minutes
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
        
        # The web link to fetch generation stats
        url = f"{BASE_URL}/generation"

        try:
            # Give the website 15 seconds to reply before timing out
            async with async_timeout.timeout(15):
                response = await self.session.get(url, headers=headers)
                
                if response.status == 401:
                    raise UpdateFailed("Invalid API Key. Please verify your Kirk Hill Dashboard API credentials.")
                elif response.status != 200:
                    raise UpdateFailed(f"API returned an unhealthy error code: {response.status}")

                # Read the JSON response from the API
                raw_payload = await response.json()
                
                if not raw_payload or "data" not in raw_payload:
                    raise UpdateFailed("API returned an unexpected or empty payload structure.")

                # This dives down into your JSON structure: data -> summary
                summary = raw_payload["data"].get("summary", {})
                if not summary:
                    raise UpdateFailed("Summary data block missing from the wind farm API response.")

                # This pulls out the exact data keys from your text and saves them for the sensors
                return {
                    "total_generation": float(summary.get("total_generation_kwh", 0.0)),
                    "capacity_factor": float(summary.get("capacity_factor_percent", 0.0)),
                    "active_turbines": int(summary.get("active_turbines", 0)),
                    "site_capacity_watts": int(summary.get("site_capacity_watts", 0)),
                    "latest_interval": str(summary.get("latest_generation_interval_end", "")),
                }

        except aiohttp.ClientError as err:
            raise UpdateFailed(f"Network error communicating with Kirk Hill API: {err}")
        except Exception as err:
            raise UpdateFailed(f"Unexpected error parsing Kirk Hill wind data: {err}")
