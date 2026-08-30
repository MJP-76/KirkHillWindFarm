"""Base entity classes for the Kirk Hill Wind Farm integration."""
from __future__ import annotations

from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity import Entity
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import CONF_OWNER_SHARE_PERCENT, SCOPE_OWNER, SCOPE_SITE
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
        self._cached_owner_share: float | None = None

    @property
    def extra_state_attributes(self) -> dict:
        return {"scope": self._scope}

    def _scope_data(self) -> dict:
        """Shortcut to the scoped payload from the coordinator."""
        return self.coordinator.data[self._scope]

    def _owner_share_pct(self) -> float | None:
        """Get owner share percentage from config, or auto-derive from generation ratio."""
        if self._cached_owner_share is not None:
            return self._cached_owner_share

        try:
            val = self._entry.options.get(CONF_OWNER_SHARE_PERCENT)
            if val is None:
                val = self._entry.data.get(CONF_OWNER_SHARE_PERCENT)
            if val is not None:
                float_val = float(val)
                if float_val > 0:
                    self._cached_owner_share = float_val
                    return float_val
        except (TypeError, ValueError):
            pass

        # Auto-derive from generation ratio (owner share is a fixed ownership percentage)
        summaries = self.coordinator.data.get("timeframe_summaries", {})
        owner_summaries = summaries.get(SCOPE_OWNER, {})
        site_summaries = summaries.get(SCOPE_SITE, {})

        for timeframe in ("today", "yesterday", "week", "month", "ytd", "year", "alltime"):
            owner_tf = owner_summaries.get(timeframe, {})
            site_tf = site_summaries.get(timeframe, {})

            owner_val = owner_tf.get("total_generation_kwh") or owner_tf.get("total_kwh")
            site_val = site_tf.get("total_generation_kwh") or site_tf.get("total_kwh")

            try:
                owner_float = float(owner_val) if owner_val is not None else None
                site_float = float(site_val) if site_val is not None else None
            except (TypeError, ValueError):
                continue

            if owner_float is not None and site_float is not None and site_float > 0:
                derived = round(owner_float / site_float * 100.0, 6)
                self._cached_owner_share = derived
                return derived

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
