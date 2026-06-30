from homeassistant.core import HomeAssistant
from homeassistant.config_entries import ConfigEntry
from .coordinator import KirkHillCoordinator

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Kirk Hill Wind Farm from a config entry."""
    hass.data.setdefault("kirkhill_wind", {})

    # Instantiate the coordinator using the UI input API key
    api_key = entry.data.get("api_key")
    coordinator = KirkHillCoordinator(hass, api_key)

    # Fetch initial data so the entities don't initialize as blank/unknown
    await coordinator.async_config_entry_first_refresh()

    # Store coordinator instance globally under this specific entry configuration
    hass.data["kirkhill_wind"][entry.entry_id] = coordinator

    # Forward the setup to the sensor platform file (sensor.py)
    await hass.config_entries.async_forward_entry_setups(entry, ["sensor"])

    return True
