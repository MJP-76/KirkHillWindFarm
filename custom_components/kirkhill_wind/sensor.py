from __future__ import annotations

from homeassistant.components.sensor import SensorEntity
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .entity import KirkHillEntity


SENSORS = {
    "power": "Power",
    "speed": "Wind Speed",
    "capacity_factor": "Capacity Factor",
}


class KirkHillSensor(KirkHillEntity, SensorEntity):
    """Wind farm sensor."""

    def __init__(self, coordinator, scope: str, key: str, device_name: str):
        super().__init__(coordinator, scope)
        self._scope = scope
        self._key = key
        self._device_name = device_name

        self._attr_unique_id = f"kirkhill_{scope}_{key}"
        self._attr_name = f"{device_name} {SENSORS[key]}"

    @property
    def native_value(self):
        data = self.coordinator.data.get(self._scope, {})
        return data.get(self._key)

    @property
    def device_info(self):
        return {
            "identifiers": {("kirkhill", self._scope)},
            "name": f"Kirk Hill {self._scope.title()}",
            "manufacturer": "Kirk Hill Energy",
        }
