from homeassistant.components.diagnostics import async_redact_data
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import DOMAIN

TO_REDACT = {"api_key"}


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant,
    entry: ConfigEntry,
):
    coordinator = entry.runtime_data

    return {
        "entry": async_redact_data(entry.data, TO_REDACT),
        "data": coordinator.data,
    }
