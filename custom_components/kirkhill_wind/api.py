from __future__ import annotations

import aiohttp


class KirkHillApi:
    """API client aligned with OpenAPI spec."""

    def __init__(self, base_url: str, api_key: str):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key

    async def get_current(self, session: aiohttp.ClientSession, scope: str):
        url = f"{self.base_url}/current"
        params = {"scope": scope}

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Accept": "application/json",
        }

        async with session.get(url, params=params, headers=headers, timeout=20) as resp:
            resp.raise_for_status()
            return await resp.json()

    async def test(self, session: aiohttp.ClientSession):
        await self.get_current(session, "owner")
