"""The Kirk Hill Wind Farm integration."""
DOMAIN = "kirkhill_wind"
PLATFORMS = ["sensor"]

async def async_setup_entry(hass, entry):
    """Set up Kirk Hill Wind Farm from a config entry."""
    # Forward the setup to sensor.py
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True

async def async_unload_entry(hass, entry):
    """Unload a config entry."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
