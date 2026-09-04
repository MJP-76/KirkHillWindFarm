"""Base entity classes for the Kirk Hill Wind Farm integration."""
from __future__ import annotations

from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity import Entity
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import SCOPE_OWNER, SCOPE_SITE
from .device import get_farm_device_info, get_turbine_device_info


def _as_float_watts(value) -> float | None:
    """Coerce a raw API capacity value to float, tolerating None/str."""
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value.replace(",", "").strip())
        except ValueError:
            return None
    return None


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

    def _owner_share_pct(self) -> float | None:
        """Owner share percentage, computed live from the API's capacity_watts.

        Owner share is watt-based: owner_capacity / site_capacity. Buying more
        watts raises the ratio automatically, so it is recomputed on every call
        rather than cached.
        """
        owner_data = self.coordinator.data.get(SCOPE_OWNER)
        site_data = self.coordinator.data.get(SCOPE_SITE)
        owner_summary = owner_data.get("summary", {}) if isinstance(owner_data, dict) else {}
        site_summary = site_data.get("summary", {}) if isinstance(site_data, dict) else {}

        owner_capacity = _as_float_watts(owner_summary.get("capacity_watts"))
        site_capacity = _as_float_watts(site_summary.get("capacity_watts"))

        if owner_capacity is not None and site_capacity and site_capacity > 0:
            return round(owner_capacity / site_capacity * 100.0, 6)
        return None


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
        hub_device_id = getattr(self.coordinator, "farm_device_id", None)
        return get_turbine_device_info(self._entry, self._turbine_id, hub_device_id)

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


TURBINE_STATUS_MAP: dict[str, str] = {
    "Turbine in operation": "running",
    "Turbine operational": "ready",
    "Turbine starting": "starting",
    "Turbine stopped: SCADA (bird and bat protection)": "curtailed",
    "Lack of wind: Wind speed too low": "no_wind",
    "Generator over temperature: Stator (measurement)": "fault_thermal",
    "Event management: switched off": "stopped",
    "Feeding fault: Pulse inhibit inverter 8": "fault_electrical",
    "Calibration of load control": "maintenance",
    "unavailable": "unavailable",
}


def turbine_status_category(state_text: str | None) -> str:
    """Map a turbine state text to a coarse status category."""
    return TURBINE_STATUS_MAP.get(state_text or "", "unknown")
