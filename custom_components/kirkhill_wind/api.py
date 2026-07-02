"""API client helper for Kirkhill Coop Wind Farm."""
import logging
import aiohttp

_LOGGER = logging.getLogger(__name__)

class KirkHillWindApi:
    """API Client to handle queries for owner/site scopes."""

    def __init__(self, base_url: str, api_key: str):
        """Initialize API parameters."""
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key

    async def _request(self, session: aiohttp.ClientSession, endpoint: str) -> dict:
        """Execute a safe authenticated request to the Kirkhill dashboard."""
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Accept": "application/json",
        }
        url = f"{self.base_url}/{endpoint.lstrip('/')}"
        
        try:
            async with session.get(url, headers=headers, timeout=15) as response:
                response.raise_for_status()
                return await response.json()
        except Exception as err:
            _LOGGER.error(f"Error accessing Kirkhill endpoint {url}: {err}")
            raise

    async def current(self, session: aiohttp.ClientSession, scope: str) -> dict:
        """Fetch real-time active tracking data for owner or site."""
        return await self._request(session, f"api/v1/{scope}/current")

    async def summary(self, session: aiohttp.ClientSession, scope: str) -> dict:
        """Fetch general telemetry metadata summary blocks."""
        return await self._request(session, f"api/v1/{scope}/summary")

    async def generation(self, session: aiohttp.ClientSession, scope: str) -> dict:
        """Fetch cumulative long-term energy counters."""
        return await self._request(session, f"api/v1/{scope}/generation")

    async def wind(self, session: aiohttp.ClientSession, scope: str) -> dict:
        """Fetch atmospheric environment metrics (e.g. wind speed)."""
        return await self._request(session, f"api/v1/{scope}/wind")

    async def turbines(self, session: aiohttp.ClientSession, scope: str) -> dict:
        """Fetch structural turbine array metrics (T1–T8)."""
        return await self._request(session, f"api/v1/{scope}/turbines")
