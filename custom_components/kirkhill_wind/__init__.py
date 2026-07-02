from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .coordinator import KirkHillCoordinator

PLATFORMS = ["sensor"]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry):
    """Set up Kirk Hill Wind Farm from a config entry."""

    coordinator = KirkHillCoordinator(hass, entry)

    await coordinator.async_config_entry_first_refresh()

    # Store coordinator (standard HA pattern)
    hass.data.setdefault(entry.domain, {})
    hass.data[entry.domain][entry.entry_id] = coordinator

    entry.runtime_data = coordinator

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry):
    """Unload Kirk Hill Wind Farm config entry."""

    unload_ok = await hass.config_entries.async_unload_platforms(
        entry,
        PLATFORMS,
    )

    if unload_ok:
        hass.data[entry.domain].pop(entry.entry_id, None)

    entry.runtime_data = None

    return unload_ok
