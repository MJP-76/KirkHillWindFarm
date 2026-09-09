from homeassistant.components.diagnostics import async_redact_data
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import SCOPE_OWNER, SCOPE_SITE

TO_REDACT = {"api_key"}


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant,
    entry: ConfigEntry,
):
    coordinator = entry.runtime_data

    data = coordinator.data
    return {
        "entry": async_redact_data(entry.data, TO_REDACT),
        "data": data,
        "summary_state": {
            "tick": data.get("tick"),
            "stale": data.get("summary_stale"),
            "failures": data.get("summary_failures"),
            "retry_at": data.get("summary_retry_at"),
            "timeframes_fetched": sorted(
                set(data.get("timeframe_summaries", {})
                    .get(SCOPE_OWNER, {}))
                | set(data.get("timeframe_summaries", {})
                    .get(SCOPE_SITE, {}))
            ),
        },
    }
