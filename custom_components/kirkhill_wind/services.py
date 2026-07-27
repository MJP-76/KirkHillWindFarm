"""Services for the Kirk Hill Wind Farm integration."""
from __future__ import annotations

import voluptuous as vol
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError

from .const import DOMAIN

SERVICE_RELOAD_INTEGRATION = "reload_integration"
SERVICE_RESET_DASHBOARD = "reset_dashboard"
ATTR_ENTRY_ID = "entry_id"
SERVICE_SCHEMA_RELOAD = vol.Schema({vol.Optional(ATTR_ENTRY_ID): str})
SERVICE_SCHEMA_RESET = vol.Schema({vol.Optional(ATTR_ENTRY_ID): str})
SERVICES_REGISTERED = "services_registered"


def _get_target_entry(hass: HomeAssistant, entry_id: str | None = None):
    """Return the target config entry, or raise if not found."""
    entries = hass.config_entries.async_entries(DOMAIN)
    if entry_id:
        target = next((e for e in entries if e.entry_id == entry_id), None)
        if target is None:
            raise HomeAssistantError(
                f"No {DOMAIN} config entry found for entry_id '{entry_id}'"
            )
        return target
    if not entries:
        raise HomeAssistantError(f"No {DOMAIN} config entry is available")
    return entries[0]


async def async_setup_services(hass: HomeAssistant) -> None:
    """Register domain services."""
    if hass.data.get(SERVICES_REGISTERED):
        return

    async def _async_reload_integration_service(call) -> None:
        target = _get_target_entry(hass, call.data.get(ATTR_ENTRY_ID))
        await hass.config_entries.async_reload(target.entry_id)

    async def _async_reset_dashboard_service(call) -> None:
        from . import async_reset_dashboard  # noqa: PLC0415

        target = _get_target_entry(hass, call.data.get(ATTR_ENTRY_ID))
        await async_reset_dashboard(hass, target)

    hass.services.async_register(
        DOMAIN,
        SERVICE_RELOAD_INTEGRATION,
        _async_reload_integration_service,
        schema=SERVICE_SCHEMA_RELOAD,
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_RESET_DASHBOARD,
        _async_reset_dashboard_service,
        schema=SERVICE_SCHEMA_RESET,
    )
    hass.data[SERVICES_REGISTERED] = True


async def async_unload_services(hass: HomeAssistant) -> None:
    """Unload domain services."""
    if not hass.data.get(SERVICES_REGISTERED):
        return

    hass.services.async_remove(DOMAIN, SERVICE_RELOAD_INTEGRATION)
    hass.services.async_remove(DOMAIN, SERVICE_RESET_DASHBOARD)
    hass.data[SERVICES_REGISTERED] = False
