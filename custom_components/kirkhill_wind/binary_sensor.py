"""Binary sensor platform for the Kirk Hill Wind Farm integration."""
from __future__ import annotations

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)

from .const import SCOPE_OWNER
from .entity import KirkHillEntity, KirkHillTurbineEntity


async def async_setup_entry(hass, entry, async_add_entities):
    coordinator = entry.runtime_data

    turbine_ids = [
        t.get("id")
        for t in coordinator.data[SCOPE_OWNER].get("turbines", [])
        if t.get("id") is not None
    ]

    entities: list = [FarmAlarmSensor(coordinator, entry)]
    entities += [TurbineActiveSensor(coordinator, entry, tid) for tid in turbine_ids]

    async_add_entities(entities)


class FarmAlarmSensor(KirkHillEntity, BinarySensorEntity):
    """On when one or more turbines are inactive."""

    _attr_name = "Alarm"
    _attr_device_class = BinarySensorDeviceClass.SAFETY

    def __init__(self, coordinator, entry):
        super().__init__(coordinator, entry, "farm_alarm")

    @property
    def is_on(self) -> bool:
        return (
            self.coordinator.data[SCOPE_OWNER]["summary"].get("inactive_turbines", 0)
            > 0
        )


class TurbineActiveSensor(KirkHillTurbineEntity, BinarySensorEntity):
    """On when the turbine status is 'active'."""

    _attr_name = "Active"
    _attr_device_class = BinarySensorDeviceClass.RUNNING

    def __init__(self, coordinator, entry, turbine_id: str):
        super().__init__(coordinator, entry, turbine_id, "active")

    @property
    def is_on(self) -> bool:
        t = self._turbine_data(SCOPE_OWNER)
        return t.get("status") == "active" if t else False
