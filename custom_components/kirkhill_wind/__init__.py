from __future__ import annotations

from .api import KirkHillApi
from .coordinator import KirkHillCoordinator


async def async_setup_entry(hass, entry):
    session = hass.helpers.aiohttp_client.async_get_clientsession(hass)

    api = KirkHillApi(
        entry.data["base_url"],
        entry.data["api_key"],
    )

    coordinator = KirkHillCoordinator(
        hass,
        api=api,
        update_interval=60,
    )

    await coordinator.async_config_entry_first_refresh()

    hass.data.setdefault("kirkhill", {})[entry.entry_id] = coordinator

    await hass.config_entries.async_forward_entry_setups(
        entry,
        ["sensor"],
    )

    return True
