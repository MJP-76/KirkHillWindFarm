"""Device info helpers for the Kirk Hill Wind Farm integration."""
from __future__ import annotations

from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo, async_get

from .const import CONF_SITE_NAME, DEFAULT_SITE_NAME, DOMAIN


def get_farm_device_info(entry) -> DeviceInfo:
    """Device info for the wind farm hub (farm-level sensors)."""
    return DeviceInfo(
        identifiers={(DOMAIN, entry.entry_id)},
        name=entry.data.get(CONF_SITE_NAME, DEFAULT_SITE_NAME),
        manufacturer="Kirk Hill Co-op",
        model="Wind Farm API",
        entry_type=DeviceEntryType.SERVICE,
    )


async def get_farm_device_id(hass, entry) -> str:
    """Resolve (creating if needed) the farm hub device's registry id.

    Used so turbine devices can link to the hub via ``via_device_id`` instead
    of the deprecated ``via_device`` tuple.
    """
    registry = async_get(hass)
    device = registry.async_get_or_create(
        config_entry_id=entry.entry_id,
        identifiers={(DOMAIN, entry.entry_id)},
        name=entry.data.get(CONF_SITE_NAME, DEFAULT_SITE_NAME),
        manufacturer="Kirk Hill Co-op",
        model="Wind Farm API",
        entry_type=DeviceEntryType.SERVICE,
    )
    return device.id


def get_turbine_device_info(entry, turbine_id: str, via_device_id: str | None = None) -> DeviceInfo:
    """Device info for an individual turbine (e.g. turbine_id='T1').

    Linked to the farm hub device via ``via_device_id`` (a device registry id),
    which replaces the deprecated ``via_device`` identifier tuple.
    """
    info: dict = {
        "identifiers": {(DOMAIN, f"{entry.entry_id}_{turbine_id}")},
        "name": f"Turbine {turbine_id}",
        "manufacturer": "Kirk Hill Co-op",
        "model": "Wind Turbine",
    }
    if via_device_id:
        info["via_device_id"] = via_device_id
    return DeviceInfo(**info)
