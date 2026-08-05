"""Base entity classes for the Kirk Hill Wind Farm integration."""
from __future__ import annotations

from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity import Entity
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .device import get_farm_device_info, get_turbine_device_info


class KirkHillEntity(CoordinatorEntity, Entity):
    """Base entity for farm-level sensors (attached to the farm hub device)."""

    _attr_has_entity_name = True

    def __init__(self, coordinator, entry, unique_suffix: str) -> None:
        super().__init__(coordinator)
        self._entry = entry
        self._attr_unique_id = f"{entry.entry_id}_{unique_suffix}"

    @property
    def device_info(self) -> DeviceInfo:
        return get_farm_device_info(self._entry)

    @property
    def available(self) -> bool:
        return self.coordinator.last_update_success


class KirkHillScopedEntity(KirkHillEntity):
    """Farm-level entity that is tied to a specific scope (owner or site)."""

    def __init__(self, coordinator, entry, scope: str, unique_suffix: str) -> None:
        super().__init__(coordinator, entry, f"{scope}_{unique_suffix}")
        self._scope = scope

    @property
    def extra_state_attributes(self) -> dict:
        return {"scope": self._scope}

    def _scope_data(self) -> dict:
        """Shortcut to the scoped payload from the coordinator."""
        return self.coordinator.data[self._scope]


class KirkHillTurbineEntity(CoordinatorEntity, Entity):
    """Base entity for per-turbine sensors, linked to a turbine device."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator,
        entry,
        turbine_id: str,
        unique_suffix: str,
    ) -> None:
        super().__init__(coordinator)
        self._entry = entry
        self._turbine_id = turbine_id  # e.g. "T1"
        self._attr_unique_id = (
            f"{entry.entry_id}_turbine_{turbine_id}_{unique_suffix}"
        )

    @property
    def device_info(self) -> DeviceInfo:
        return get_turbine_device_info(self._entry, self._turbine_id)

    def _turbine_data(self, scope: str) -> dict | None:
        """Return the turbine dict for the given scope, or None if missing."""
        turbines = self.coordinator.data[scope].get("turbines", [])
        for t in turbines:
            if t.get("id") == self._turbine_id:
                return t
        return None

    def _turbine_generation_data(self) -> dict:
        """Return the per-turbine generation/rotor metrics dict, or empty if missing."""
        return self.coordinator.data.get("turbine_generation", {}).get(
            self._turbine_id, {}
        )

    @property
    def available(self) -> bool:
        return self.coordinator.last_update_success


class KirkHillScopedTurbineEntity(KirkHillTurbineEntity):
    """Per-turbine entity tied to a specific scope."""

    def __init__(
        self,
        coordinator,
        entry,
        turbine_id: str,
        scope: str,
        unique_suffix: str,
    ) -> None:
        super().__init__(coordinator, entry, turbine_id, f"{scope}_{unique_suffix}")
        self._scope = scope

    @property
    def extra_state_attributes(self) -> dict:
        return {"scope": self._scope}
