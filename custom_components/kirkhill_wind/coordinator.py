from datetime import timedelta
import logging
import async_timeout
import aiohttp

from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession

_LOGGER = logging.getLogger(__name__)

BASE_URL = "https://dashboard.kirkhillcoop.org/api/v1"
# This is the correct base API web path you updated earlier

class KirkHillCoordinator(DataUpdateCoordinator):
    """Class to manage fetching live Kirk Hill Wind Farm API data."""

    def __init__(self, hass: HomeAssistant, api_key: str) -> None:
        """Initialize the coordinator."""
        self.api_key = api_key
        self.session = async_get_clientsession(hass)
        
        # Poll the API for updates every 5 minutes
        super().__init__(
            hass,
            _LOGGER,
            name="Kirk Hill Wind Farm",
            update_interval=timedelta(minutes=5),
        )

    async def _async_update_data(self) -> dict:
        """Fetch and parse live data from the Kirk Hill Wind Farm API."""
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Accept": "application/json",
        }
        
        url = f"{BASE_URL}/generation"

        try:
            async with async_timeout.timeout(15):
                response = await self.session.get(url, headers=headers)
                
                if response.status == 401:
                    raise UpdateFailed("Invalid API Key. Please verify your credentials.")
                elif response.status != 200:
                    raise UpdateFailed(f"API returned an error code: {response.status}")

                # 1. This reads the raw payload you shared with me
                raw_payload = await response.json()
                
                if not raw_payload or "data" not in raw_payload:
                    raise UpdateFailed("API returned an unexpected or empty payload structure.")

                # 2. This splits your JSON into the two target sections: window and summary
                window = raw_payload["data"].get("window", {})
                summary = raw_payload["data"].get("summary", {})

                # 3. This maps out every single variable so sensor.py can find them easily
                return {
                    # Variables from the "window" block
                    "range": str(window.get("range", "")),
                    "from_time": str(window.get("from", "")),
                    "to_time": str(window.get("to", "")),
                    "bucket": str(window.get("bucket", "")),
                    "scope": str(window.get("scope", "")),
                    "timezone": str(window.get("timezone", "")),
                    
                    # Variables from the "summary" block
                    "total_generation": float(summary.get("total_generation_kwh", 0.0)),
                    "capacity_factor": float(summary.get("capacity_factor_percent", 0.0)),
                    "active_turbines": int(summary.get("active_turbines", 0)),
                    "site_capacity_watts": int(summary.get("site_capacity_watts", 0)),
                    "latest_interval": str(summary.get("latest_generation_interval_end", "")),
                    "import_status": str(summary.get("latest_import_status", "")),
                }

        except aiohttp.ClientError as err:
            raise UpdateFailed(f"Network error communicating with Kirk Hill API: {err}")
        except Exception as err:
            raise UpdateFailed(f"Unexpected error parsing Kirk Hill wind data: {err}")
