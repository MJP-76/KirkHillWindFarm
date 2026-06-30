import logging
from homeassistant.core import HomeAssistant
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform

from .coordinator import KirkHillCoordinator

_LOGGER = logging.getLogger(__name__)

# This tells Home Assistant that this integration has a sensor platform (sensor.py)
PLATFORMS: list[Platform] = [Platform.SENSOR]

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Kirk Hill Wind Farm from a config entry (UI Setup)."""
    # Create an empty dictionary in Home Assistant memory to hold our integration data
    hass.data.setdefault("kirkhill_wind", {})

    # Pull the API key that the user typed into the integration's UI config entry
    api_key = entry.data.get("api_key")
    if not api_key:
        _LOGGER.error("No API key found in the configuration entry")
        return False

    # Initialize the Data Update Coordinator using your custom file
    coordinator = KirkHillCoordinator(hass, api_key)

    # Make the integration fetch its very first block of live wind data before creating sensors.
    # This prevents your sensors from showing up as "unknown" on startup.
    await coordinator.async_config_entry_first_refresh()

    # Save this running coordinator instance in Home Assistant's global memory
    hass.data["kirkhill_wind"][entry.entry_id] = coordinator

    # Forward the setup instruction down to sensor.py to create the entities
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry when the user removes or disables the integration."""
    # This cleans up and turns off the sensor platforms cleanly
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    
    if unload_ok:
        # Remove the coordinator instance from memory
        hass.data["kirkhill_wind"].pop(entry.entry_id)

    return unload_ok
