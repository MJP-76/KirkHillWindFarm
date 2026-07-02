"""The Kirk Hill Wind Farm integration."""
from __future__ import annotations

import asyncio
from datetime import timedelta
from typing import Any
import aiohttp

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import BASE_URL, CONF_API_KEY, DOMAIN, LOGGER

PLATFORMS: list[str] = ["sensor"]

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Kirk Hill Wind Farm from a config entry."""
    session = async_get_clientsession(hass)
    api_key = entry.data.get(CONF_API_KEY)

    async def async_get_api_data() -> dict[str, Any]:
        """Fetch current and summary readings safely, gracefully ignoring scope 404s."""
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "Accept": "application/json"
        }

        async def fetch_endpoint(path: str, params: dict[str, str]) -> Any:
            url = f"{BASE_URL}{path}"
            try:
                async with session.get(url, headers=headers, params=params, timeout=10) as response:
                    if response.status in (401, 403):
                        raise UpdateFailed("Unauthorised: Invalid or revoked API key.")
                    if response.status == 423:
                        raise UpdateFailed("Password change required on Kirk Hill dashboard.")
                    if response.status == 404:
                        LOGGER.warning("Endpoint %s with params %s returned 404. Key may lack scope access.", path, params)
                        return None
                    if response.status != 200:
                        raise UpdateFailed(f"API endpoint {path} returned status {response.status}")
                    return await response.json()
            except aiohttp.ClientError as err:
                raise UpdateFailed(f"Network error on {path}: {err}") from err

        # Run all 4 endpoint requests concurrently
        results = await asyncio.gather(
            fetch_endpoint("/api/v1/current", {"scope": "owner"}),
            fetch_endpoint("/api/v1/current", {"scope": "site"}),
            fetch_endpoint("/api/v1/summary", {"scope": "owner", "range": "7d"}),
            fetch_endpoint("/api/v1/summary", {"scope": "site", "range": "7d"}),
        )

        # Unpack the list results matching the exact order they were gathered
        return {
            "current_owner": results[0],
            "current_site": results[1],
            "summary_owner": results[2],
            "summary_site": results[3],
        }

    coordinator = DataUpdateCoordinator(
        hass,
        LOGGER,
        name="Kirk Hill Wind Farm API",
        update_method=async_get_api_data,
        update_interval=timedelta(minutes=5),
    )

    await coordinator.async_config_entry_first_refresh()

    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN][entry.entry_id] = coordinator

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True

async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry safely."""
    if unload_ok := await hass.config_entries.async_unload_platforms(entry, PLATFORMS):
        hass.data[DOMAIN].pop(entry.entry_id)
    return unload_ok
