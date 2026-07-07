"""Services for the Kirk Hill Wind Farm integration."""
from __future__ import annotations

import voluptuous as vol
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError

from .const import DOMAIN

SERVICE_RELOAD_INTEGRATION = "reload_integration"
ATTR_ENTRY_ID = "entry_id"
SERVICE_SCHEMA_RELOAD = vol.Schema({vol.Optional(ATTR_ENTRY_ID): str})
SERVICES_REGISTERED = "services_registered"


async def async_setup_services(hass: HomeAssistant) -> None:
    """Register domain services."""
    if hass.data.get(SERVICES_REGISTERED):
        return

    async def _async_reload_integration_service(call) -> None:
        entry_id = call.data.get(ATTR_ENTRY_ID)
        target = None
        entries = hass.config_entries.async_entries(DOMAIN)
        if entry_id:
            target = next((entry for entry in entries if entry.entry_id == entry_id), None)
            if target is None:
                raise HomeAssistantError(
                    f"No {DOMAIN} config entry found for entry_id '{entry_id}'"
                )
        else:
            if not entries:
                raise HomeAssistantError(f"No {DOMAIN} config entry is available to reload")
            target = entries[0]

        await hass.config_entries.async_reload(target.entry_id)

    hass.services.async_register(
        DOMAIN,
        SERVICE_RELOAD_INTEGRATION,
        _async_reload_integration_service,
        schema=SERVICE_SCHEMA_RELOAD,
    )
    hass.data[SERVICES_REGISTERED] = True


async def async_unload_services(hass: HomeAssistant) -> None:
    """Unload domain services."""
    if not hass.data.get(SERVICES_REGISTERED):
        return

    hass.services.async_remove(DOMAIN, SERVICE_RELOAD_INTEGRATION)
    hass.data[SERVICES_REGISTERED] = False
