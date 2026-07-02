from .api import KirkHillApi
from .coordinator import KirkHillCoordinator

DOMAIN = "kirkhill_wind"
PLATFORMS = ["sensor"]


async def async_setup_entry(hass, entry):
    session = hass.helpers.aiohttp_client.async_get_clientsession(hass)

    api = KirkHillApi(entry.data["base_url"], entry.data["api_key"])

    coordinator = KirkHillCoordinator(hass, api, 60)

    await coordinator.async_config_entry_first_refresh()

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = coordinator

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    return True


async def async_unload_entry(hass, entry):
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
