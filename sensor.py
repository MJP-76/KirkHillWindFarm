from homeassistant.helpers.device_registry import DeviceInfo

from .const import DOMAIN


def get_device_info(entry, scope: str):
    return DeviceInfo(
        identifiers={(DOMAIN, f"{entry.entry_id}_{scope}")},
        name=f"Kirk Hill {scope.capitalize()}",
        manufacturer="Kirk Hill Co-op",
        model="Wind Farm Data Feed",
        entry_type="service",
    )
