from __future__ import annotations

from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.helpers.entity import Entity

class KirkHillEntity(CoordinatorEntity, Entity):
    """Base entity."""

    _attr_has_entity_name = True

    def __init__(self, coordinator, device_key: str):
        super().__init__(coordinator)
        self._device_key = device_key

    @property
    def available(self):
        return self.coordinator.last_update_success
