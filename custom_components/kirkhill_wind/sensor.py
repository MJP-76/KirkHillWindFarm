import logging

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .device import get_device_info
from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)


SCOPE_LABEL = {
    "owner": "Owner",
    "site": "Site",
}


def _get_scopes_for_entity_setup(data: dict) -> list[str]:
    """Return scopes to expose as entities, deduplicating identical payloads."""
    owner_data = data.get("owner")
    site_data = data.get("site")

    scopes = []
    if isinstance(owner_data, dict):
        scopes.append("owner")
    if isinstance(site_data, dict):
        scopes.append("site")

    if (
        len(scopes) == 2
        and owner_data == site_data
    ):
        _LOGGER.warning(
            "Owner and site payloads are identical; creating only site entities to avoid duplicates."
        )
        return ["site"]

    return scopes


# =========================
# SAFE SETUP
# =========================

async def async_setup_entry(hass, entry, async_add_entities):
    coordinator = entry.runtime_data

    entities = []

    # 🔒 SAFE READ (no assumption coordinator.data exists fully yet)
    data = coordinator.data or {}

    for scope in _get_scopes_for_entity_setup(data):
        scope_data = data.get(scope)

        # Base sensors
        entities.extend([
            KirkHillCapacityFactor(coordinator, entry, scope),
            KirkHillGeneration(coordinator, entry, scope),
            KirkHillWindSpeed(coordinator, entry, scope),
            KirkHillCurrentPower(coordinator, entry, scope),
            KirkHillCurrentCapacityFactor(coordinator, entry, scope),
            KirkHillCurrentWindSpeed(coordinator, entry, scope),
            KirkHillActiveTurbines(coordinator, entry, scope),
        ])

        # Turbines (safe check) - API returns turbines as a list
        turbines_data = scope_data.get("turbines", {})
        turbines = turbines_data.get("turbines", [])

        if isinstance(turbines, list):
            for turbine in turbines:
                if isinstance(turbine, dict) and "id" in turbine:
                    entities.append(
                        KirkHillTurbineGeneration(
                            coordinator,
                            entry,
                            scope,
                            turbine["id"],
                        )
                    )

        current_data = scope_data.get("current", {})
        current_turbines = current_data.get("turbines", [])
        if isinstance(current_turbines, list):
            for turbine in current_turbines:
                if isinstance(turbine, dict) and "id" in turbine:
                    entities.append(
                        KirkHillTurbineCurrentPower(
                            coordinator,
                            entry,
                            scope,
                            turbine["id"],
                        )
                    )
                    entities.append(
                        KirkHillTurbineStatus(
                            coordinator,
                            entry,
                            scope,
                            turbine["id"],
                        )
                    )

    async_add_entities(entities)


# =========================
# BASE CLASS
# =========================

class KirkHillBaseSensor(CoordinatorEntity, SensorEntity):
    def __init__(self, coordinator, entry, scope: str):
        super().__init__(coordinator)
        self.entry = entry
        self.scope = scope

    @property
    def device_info(self):
        return get_device_info(self.entry, self.scope)

    @property
    def scope_data(self):
        data = self.coordinator.data or {}
        return data.get(self.scope, {}) or {}

    @property
    def scope_label(self):
        return SCOPE_LABEL.get(self.scope, self.scope)


# =========================
# CORE SENSORS
# =========================

class KirkHillCapacityFactor(KirkHillBaseSensor):
    """Capacity factor sensor - from summary endpoint."""
    _attr_native_unit_of_measurement = "%"
    _attr_state_class = SensorStateClass.MEASUREMENT

    @property
    def name(self):
        return f"Kirk Hill {self.scope_label} Capacity Factor"

    @property
    def unique_id(self):
        return f"{DOMAIN}_{self.entry.entry_id}_{self.scope}_capacity_factor"

    @property
    def native_value(self):
        # Capacity factor is in summary.data.summary.capacity_factor_percent
        summary_data = self.scope_data.get("summary", {})
        summary = summary_data.get("summary", {})
        cf = summary.get("capacity_factor_percent")
        
        if cf is not None and isinstance(cf, (int, float)):
            return cf
        return None


class KirkHillGeneration(KirkHillBaseSensor):
    """Total generation sensor - from generation endpoint."""
    _attr_native_unit_of_measurement = "kWh"
    _attr_state_class = SensorStateClass.TOTAL_INCREASING
    _attr_device_class = SensorDeviceClass.ENERGY

    @property
    def name(self):
        return f"Kirk Hill {self.scope_label} Generation"

    @property
    def unique_id(self):
        return f"{DOMAIN}_{self.entry.entry_id}_{self.scope}_generation"

    @property
    def native_value(self):
        # Total generation is in generation.data.summary.total_generation_kwh
        generation_data = self.scope_data.get("generation", {})
        summary = generation_data.get("summary", {})
        generation = summary.get("total_generation_kwh")
        
        if generation is not None and isinstance(generation, (int, float)):
            return generation
        return None


class KirkHillWindSpeed(KirkHillBaseSensor):
    """Current wind speed sensor - gets latest from wind-speed endpoint."""
    _attr_native_unit_of_measurement = "m/s"
    _attr_state_class = SensorStateClass.MEASUREMENT

    @property
    def name(self):
        return f"Kirk Hill {self.scope_label} Wind Speed"

    @property
    def unique_id(self):
        return f"{DOMAIN}_{self.entry.entry_id}_{self.scope}_wind_speed"

    @property
    def native_value(self):
        # Wind speed is in wind.data.series[], get the latest
        wind_data = self.scope_data.get("wind", {})
        series = wind_data.get("series", [])
        
        if isinstance(series, list) and len(series) > 0:
            # Get the last entry (most recent)
            latest = series[-1]
            if isinstance(latest, dict):
                speed = latest.get("wind_speed_mps")
                if speed is not None and isinstance(speed, (int, float)):
                    return speed
        
        return None


class KirkHillCurrentPower(KirkHillBaseSensor):
    """Current total power sensor - from current endpoint."""
    _attr_native_unit_of_measurement = "kW"
    _attr_state_class = SensorStateClass.MEASUREMENT

    @property
    def name(self):
        return f"Kirk Hill {self.scope_label} Current Power"

    @property
    def unique_id(self):
        return f"{DOMAIN}_{self.entry.entry_id}_{self.scope}_current_power"

    @property
    def native_value(self):
        current_data = self.scope_data.get("current", {})
        summary = current_data.get("summary", {})
        power = summary.get("total_power_kw")
        if power is not None and isinstance(power, (int, float)):
            return power
        return None


class KirkHillCurrentCapacityFactor(KirkHillBaseSensor):
    """Current capacity factor sensor - from current endpoint."""
    _attr_native_unit_of_measurement = "%"
    _attr_state_class = SensorStateClass.MEASUREMENT

    @property
    def name(self):
        return f"Kirk Hill {self.scope_label} Current Capacity Factor"

    @property
    def unique_id(self):
        return f"{DOMAIN}_{self.entry.entry_id}_{self.scope}_current_capacity_factor"

    @property
    def native_value(self):
        current_data = self.scope_data.get("current", {})
        summary = current_data.get("summary", {})
        cf = summary.get("capacity_factor_percent")
        if cf is not None and isinstance(cf, (int, float)):
            return cf
        return None


class KirkHillCurrentWindSpeed(KirkHillBaseSensor):
    """Current wind speed sensor - from current endpoint."""
    _attr_native_unit_of_measurement = "m/s"
    _attr_state_class = SensorStateClass.MEASUREMENT

    @property
    def name(self):
        return f"Kirk Hill {self.scope_label} Current Wind Speed"

    @property
    def unique_id(self):
        return f"{DOMAIN}_{self.entry.entry_id}_{self.scope}_current_wind_speed"

    @property
    def native_value(self):
        current_data = self.scope_data.get("current", {})
        summary = current_data.get("summary", {})
        speed = summary.get("wind_speed_mps")
        if speed is not None and isinstance(speed, (int, float)):
            return speed
        return None


class KirkHillActiveTurbines(KirkHillBaseSensor):
    """Current active turbine count sensor - from current endpoint."""
    _attr_state_class = SensorStateClass.MEASUREMENT

    @property
    def name(self):
        return f"Kirk Hill {self.scope_label} Active Turbines"

    @property
    def unique_id(self):
        return f"{DOMAIN}_{self.entry.entry_id}_{self.scope}_active_turbines"

    @property
    def native_value(self):
        current_data = self.scope_data.get("current", {})
        summary = current_data.get("summary", {})
        active = summary.get("active_turbines")
        if active is not None and isinstance(active, int):
            return active
        return None


# =========================
# TURBINE SENSORS
# =========================

class KirkHillTurbineGeneration(KirkHillBaseSensor):
    """Per-turbine generation sensor - from turbines endpoint."""
    _attr_native_unit_of_measurement = "kWh"
    _attr_state_class = SensorStateClass.TOTAL_INCREASING
    _attr_device_class = SensorDeviceClass.ENERGY

    def __init__(self, coordinator, entry, scope, turbine_id):
        super().__init__(coordinator, entry, scope)
        self.turbine_id = turbine_id

    @property
    def name(self):
        return f"Kirk Hill {self.scope_label} Turbine {self.turbine_id} Generation"

    @property
    def unique_id(self):
        return (
            f"{DOMAIN}_{self.entry.entry_id}_{self.scope}_"
            f"turbine_{self.turbine_id}_generation"
        )

    @property
    def native_value(self):
        # Turbines are in turbines.data.turbines[] as a list
        turbines_data = self.scope_data.get("turbines", {})
        turbines = turbines_data.get("turbines", [])

        if not isinstance(turbines, list):
            return None

        # Find the turbine with matching ID
        for turbine in turbines:
            if isinstance(turbine, dict) and turbine.get("id") == self.turbine_id:
                generation = turbine.get("generation_kwh")
                if generation is not None and isinstance(generation, (int, float)):
                    return generation

        return None


class KirkHillTurbineCurrentPower(KirkHillBaseSensor):
    """Per-turbine current power sensor - from current endpoint."""
    _attr_native_unit_of_measurement = "kW"
    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(self, coordinator, entry, scope, turbine_id):
        super().__init__(coordinator, entry, scope)
        self.turbine_id = turbine_id

    @property
    def name(self):
        return f"Kirk Hill {self.scope_label} Turbine {self.turbine_id} Current Power"

    @property
    def unique_id(self):
        return (
            f"{DOMAIN}_{self.entry.entry_id}_{self.scope}_"
            f"turbine_{self.turbine_id}_current_power"
        )

    @property
    def native_value(self):
        current_data = self.scope_data.get("current", {})
        turbines = current_data.get("turbines", [])

        if not isinstance(turbines, list):
            return None

        for turbine in turbines:
            if isinstance(turbine, dict) and turbine.get("id") == self.turbine_id:
                power = turbine.get("power_kw")
                if power is not None and isinstance(power, (int, float)):
                    return power

        return None


class KirkHillTurbineStatus(KirkHillBaseSensor):
    """Per-turbine status sensor - from current endpoint."""

    def __init__(self, coordinator, entry, scope, turbine_id):
        super().__init__(coordinator, entry, scope)
        self.turbine_id = turbine_id

    @property
    def name(self):
        return f"Kirk Hill {self.scope_label} Turbine {self.turbine_id} Status"

    @property
    def unique_id(self):
        return (
            f"{DOMAIN}_{self.entry.entry_id}_{self.scope}_"
            f"turbine_{self.turbine_id}_status"
        )

    @property
    def native_value(self):
        current_data = self.scope_data.get("current", {})
        turbines = current_data.get("turbines", [])

        if not isinstance(turbines, list):
            return None

        for turbine in turbines:
            if isinstance(turbine, dict) and turbine.get("id") == self.turbine_id:
                status = turbine.get("status")
                if isinstance(status, str):
                    return status

        return None
