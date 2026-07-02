"""API client helper for Kirkhill Coop Wind Farm."""
import logging
import aiohttp

_LOGGER = logging.getLogger(__name__)

class KirkHillWindApi:
    """API Client to handle queries for owner/site scopes."""

    def __init__(self, base_url: str, api_key: str):
        """Initialize API parameters."""
        # Clean the base URL and ensure there are no trailing slashes
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
            _LOGGER.debug(f"Fetching Kirkhill API endpoint: {url}")
            async with session.get(url, headers=headers, timeout=15) as response:
                response.raise_for_status()
                return await response.json()
        except Exception as err:
            _LOGGER.error(f"Error accessing Kirkhill endpoint {url}: {err}")
            raise

    async def current(self, session: aiohttp.ClientSession, scope: str) -> dict:
        """Fetch real-time active tracking data for owner or site."""
        # Maps directly to: api/v1/owner-current OR api/v1/site-current
        return await self._request(session, f"api/v1/{scope}-current")

    async def summary(self, session: aiohttp.ClientSession, scope: str) -> dict:
        """Fetch general telemetry metadata summary blocks."""
        # Maps directly to: api/v1/owner-summary OR api/v1/site-summary
        return await self._request(session, f"api/v1/{scope}-summary")

    async def generation(self, session: aiohttp.ClientSession, scope: str) -> dict:
        """Fetch cumulative long-term energy counters."""
        # Maps directly to: api/v1/owner-generation OR api/v1/site-generation
        return await self._request(session, f"api/v1/{scope}-generation")

    async def wind(self, session: aiohttp.ClientSession, scope: str) -> dict:
        """Fetch atmospheric environment metrics (e.g. wind speed)."""
        # Maps directly to: api/v1/owner-wind OR api/v1/site-wind
        return await self._request(session, f"api/v1/{scope}-wind")

    async def turbines(self, session: aiohttp.ClientSession, scope: str) -> dict:
        """Fetch structural turbine array metrics (T1–T8)."""
        # Maps directly to: api/v1/owner-turbines OR api/v1/site-turbines
        return await self._request(session, f"api/v1/{scope}-turbines")
