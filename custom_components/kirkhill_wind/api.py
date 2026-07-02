import aiohttp
import logging

_LOGGER = logging.getLogger(__name__)


class KirkHillApiError(Exception):
    pass


class KirkHillWindApi:
    def __init__(self, base_url: str, api_key: str):
        self._base_url = base_url
        self._api_key = api_key

    async def request(self, session, path, params=None):
        url = f"{self._base_url}{path}"

        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Accept": "application/json",
        }

        try:
            _LOGGER.debug(f"API request to {url} with params {params}")
            async with session.get(url, headers=headers, params=params) as resp:
                _LOGGER.debug(f"API response status: {resp.status}")
                if resp.status >= 400:
                    error_text = await resp.text()
                    _LOGGER.error(f"API error {resp.status}: {error_text}")
                    raise KirkHillApiError(error_text)
                response = await resp.json()
                _LOGGER.debug(f"Raw API response received")
                # Extract the data field from the response
                extracted = response.get("data", response)
                _LOGGER.debug(f"Extracted data from response")
                return extracted
        except Exception as err:
            _LOGGER.error(f"API request failed: {err}", exc_info=True)
            raise

    async def summary(self, session, scope):
        return await self.request(session, "/api/v1/summary", {"scope": scope})

    async def generation(self, session, scope):
        return await self.request(session, "/api/v1/generation", {"scope": scope})

    async def wind(self, session, scope):
        return await self.request(session, "/api/v1/wind-speed", {"scope": scope})

    async def turbines(self, session, scope):
        return await self.request(session, "/api/v1/turbines", {"scope": scope})
