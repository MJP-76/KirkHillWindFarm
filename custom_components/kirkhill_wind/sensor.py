"""Sensor platform for the Kirk Hill Wind Farm integration."""
from __future__ import annotations

from datetime import date

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.const import PERCENTAGE, UnitOfEnergy, UnitOfPower, UnitOfSpeed

from .const import (
    CONF_OWNER_PROJECTED_ANNUAL_EARNINGS_GBP,
    CONF_SITE_PROJECTED_ANNUAL_EARNINGS_GBP,
    DEFAULT_OWNER_PROJECTED_ANNUAL_EARNINGS_GBP,
    DEFAULT_SITE_PROJECTED_ANNUAL_EARNINGS_GBP,
    SCOPE_OWNER,
    SCOPE_SITE,
    SCOPES,
    TIMEFRAME_ORDER,
)
from .entity import (
    KirkHillEntity,
    KirkHillScopedEntity,
    KirkHillScopedTurbineEntity,
    KirkHillTurbineEntity,
)

TIMEFRAME_LABELS = {
    "yesterday": "Generation (yesterday)",
    "today": "Generation (today)",
    "week": "Generation (week)",
    "month": "Generation (month)",
    "ytd": "Generation (ytd)",
    "year": "Generation (year)",
    "alltime": "Generation (alltime)",
}


def _as_float(value) -> float | None:
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        normalized = value.replace(",", "").strip()
        if not normalized:
            return None
        try:
            return float(normalized)
        except ValueError:
            return None
    return None


async def async_setup_entry(hass, entry, async_add_entities):
    coordinator = entry.runtime_data

    turbine_ids = [t["id"] for t in coordinator.data[SCOPE_OWNER].get("turbines", [])]

    entities: list = [
        *[FarmPowerSensor(coordinator, entry, scope) for scope in SCOPES],
        *[FarmCapacityFactorSensor(coordinator, entry, scope) for scope in SCOPES],
        *[
            FarmGenerationByTimeframeSensor(coordinator, entry, scope, timeframe)
            for scope in SCOPES
            for timeframe in TIMEFRAME_ORDER
        ],
        *[
            GenerationValueByTimeframeSensor(coordinator, entry, scope, timeframe)
            for timeframe in TIMEFRAME_ORDER
            for scope in SCOPES
        ],
        FarmWindSpeedSensor(coordinator, entry),
        OpenMeteoForecastWindSpeedSensor(
            coordinator, entry, "next_hour_wind_speed_mps", "Open-Meteo forecast wind (next hour)"
        ),
        OpenMeteoForecastWindSpeedSensor(
            coordinator, entry, "next_3h_avg_wind_speed_mps", "Open-Meteo forecast wind (next 3h avg)"
        ),
        OpenMeteoForecastWindSpeedSensor(
            coordinator, entry, "next_24h_avg_wind_speed_mps", "Open-Meteo forecast wind (next 24h avg)"
        ),
        FarmActiveTurbinesSensor(coordinator, entry),
        FarmInactiveTurbinesSensor(coordinator, entry),
    ]

    for tid in turbine_ids:
        entities += [TurbinePowerSensor(coordinator, entry, tid, scope) for scope in SCOPES]
        entities += [
            TurbineCapacityFactorSensor(coordinator, entry, tid, scope) for scope in SCOPES
        ]
        entities.append(TurbineWindSpeedSensor(coordinator, entry, tid))
        entities.append(TurbineStateSensor(coordinator, entry, tid))

    async_add_entities(entities)


class FarmPowerSensor(KirkHillScopedEntity, SensorEntity):
    _attr_device_class = SensorDeviceClass.POWER
    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(self, coordinator, entry, scope: str):
        super().__init__(coordinator, entry, scope, "farm_power")
        self._attr_name = f"Power ({scope})"
        self._attr_native_unit_of_measurement = (
            "MW" if scope == SCOPE_SITE else UnitOfPower.KILO_WATT
        )

    @property
    def native_value(self):
        value = _as_float(self._scope_data()["summary"].get("total_power_kw"))
        if value is None:
            return None
        if self._scope == SCOPE_SITE:
            return value / 1000
        return value


class FarmCapacityFactorSensor(KirkHillScopedEntity, SensorEntity):
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_native_unit_of_measurement = PERCENTAGE
    _attr_icon = "mdi:gauge"

    def __init__(self, coordinator, entry, scope: str):
        super().__init__(coordinator, entry, scope, "farm_capacity_factor")
        self._attr_name = f"Capacity factor ({scope})"

    @property
    def native_value(self):
        timeframe_summary = (
            self.coordinator.data.get("timeframe_summaries", {})
            .get(self._scope, {})
            .get("today", {})
        )
        value = _as_float(timeframe_summary.get("capacity_factor_percent"))
        if value is not None:
            return value
        return _as_float(self._scope_data()["summary"].get("capacity_factor_percent"))


class FarmGenerationByTimeframeSensor(KirkHillScopedEntity, SensorEntity):
    _attr_device_class = SensorDeviceClass.ENERGY
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_native_unit_of_measurement = UnitOfEnergy.KILO_WATT_HOUR
    _attr_suggested_display_precision = 2

    def __init__(self, coordinator, entry, scope: str, timeframe: str):
        super().__init__(coordinator, entry, scope, f"farm_generation_{timeframe}")
        self._timeframe = timeframe
        scope_label = scope.capitalize()
        label = TIMEFRAME_LABELS.get(timeframe, f"Generation ({timeframe})")
        self._attr_name = f"{label} ({scope_label})"

    def _generation_kwh(self) -> float | None:
        summary = (
            self.coordinator.data.get("timeframe_summaries", {})
            .get(self._scope, {})
            .get(self._timeframe, {})
        )
        value = _as_float(summary.get("total_generation_kwh"))
        if value is not None:
            return value
        return _as_float(summary.get("total_kwh"))

    @property
    def native_value(self):
        return self._generation_kwh()

    @property
    def extra_state_attributes(self) -> dict:
        attrs = super().extra_state_attributes
        value_kwh = self._generation_kwh()
        attrs["timeframe"] = self._timeframe
        attrs["generation_source"] = "api_dynamic"
        attrs["raw_generation_kwh"] = value_kwh
        if value_kwh is None:
            attrs["display_unit"] = UnitOfEnergy.KILO_WATT_HOUR
            attrs["display_value"] = None
        elif value_kwh >= 1000:
            attrs["display_unit"] = UnitOfEnergy.MEGA_WATT_HOUR
            attrs["display_value"] = round(value_kwh / 1000, 2)
        else:
            attrs["display_unit"] = UnitOfEnergy.KILO_WATT_HOUR
            attrs["display_value"] = round(value_kwh, 2)
        return attrs


class GenerationValueByTimeframeSensor(KirkHillScopedEntity, SensorEntity):
    _attr_device_class = SensorDeviceClass.MONETARY
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_native_unit_of_measurement = "GBP"
    _attr_suggested_display_precision = 2
    _attr_icon = "mdi:cash"

    def __init__(self, coordinator, entry, scope: str, timeframe: str):
        super().__init__(coordinator, entry, scope, f"farm_generation_value_{timeframe}")
        self._timeframe = timeframe
        scope_label = scope.capitalize()
        label = TIMEFRAME_LABELS.get(timeframe, f"Projected ({timeframe})")
        self._attr_name = f"{label} projected value ({scope_label})"

    def _annual_projected_gbp(self) -> float:
        if self._scope == SCOPE_OWNER:
            key = CONF_OWNER_PROJECTED_ANNUAL_EARNINGS_GBP
            default = DEFAULT_OWNER_PROJECTED_ANNUAL_EARNINGS_GBP
        else:
            key = CONF_SITE_PROJECTED_ANNUAL_EARNINGS_GBP
            default = DEFAULT_SITE_PROJECTED_ANNUAL_EARNINGS_GBP
        return float(self._entry.options.get(key, self._entry.data.get(key, default)))

    def _projection_factor(self) -> float:
        if self._timeframe in ("yesterday", "today"):
            return 1 / 365
        if self._timeframe == "week":
            return 7 / 365
        if self._timeframe == "month":
            return 30 / 365
        if self._timeframe == "ytd":
            return date.today().timetuple().tm_yday / 365
        if self._timeframe == "year":
            return 1.0
        if self._timeframe == "alltime":
            return 20.0
        return 0.0

    @property
    def native_value(self):
        return round(self._annual_projected_gbp() * self._projection_factor(), 2)

    @property
    def extra_state_attributes(self) -> dict:
        attrs = super().extra_state_attributes
        attrs["timeframe"] = self._timeframe
        attrs["projection_basis"] = "projected_non_dynamic"
        attrs["projected_annual_gbp"] = self._annual_projected_gbp()
        attrs["projection_factor"] = self._projection_factor()
        return attrs


class FarmWindSpeedSensor(KirkHillEntity, SensorEntity):
    _attr_name = "Wind speed"
    _attr_device_class = SensorDeviceClass.WIND_SPEED
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_native_unit_of_measurement = UnitOfSpeed.METERS_PER_SECOND

    def __init__(self, coordinator, entry):
        super().__init__(coordinator, entry, "farm_wind_speed")

    @property
    def native_value(self):
        value = _as_float(self.coordinator.data.get("wind_speed_today"))
        if value is not None:
            return value
        return _as_float(self.coordinator.data[SCOPE_OWNER]["summary"].get("wind_speed_mps"))


class OpenMeteoForecastWindSpeedSensor(KirkHillEntity, SensorEntity):
    """Forecast wind-speed sensor from Open-Meteo (non-authoritative)."""

    _attr_device_class = SensorDeviceClass.WIND_SPEED
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_native_unit_of_measurement = UnitOfSpeed.METERS_PER_SECOND
    _attr_icon = "mdi:weather-windy"

    def __init__(self, coordinator, entry, forecast_key: str, name: str):
        super().__init__(coordinator, entry, f"open_meteo_{forecast_key}")
        self._forecast_key = forecast_key
        self._attr_name = name

    @property
    def native_value(self):
        value = (
            self.coordinator.data.get("open_meteo_forecast", {}).get(self._forecast_key)
        )
        return _as_float(value)

    @property
    def extra_state_attributes(self) -> dict:
        forecast = self.coordinator.data.get("open_meteo_forecast", {})
        return {
            "source": "open_meteo_forecast_only",
            "authoritative_actual_source": "kirkhill_api",
            "provider": forecast.get("provider"),
            "model": forecast.get("model"),
            "forecast_points": forecast.get("forecast_points"),
        }


class FarmActiveTurbinesSensor(KirkHillEntity, SensorEntity):
    _attr_name = "Active turbines"
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_icon = "mdi:wind-turbine"

    def __init__(self, coordinator, entry):
        super().__init__(coordinator, entry, "farm_active_turbines")

    @property
    def native_value(self):
        return self.coordinator.data[SCOPE_OWNER]["summary"].get("active_turbines")


class FarmInactiveTurbinesSensor(KirkHillEntity, SensorEntity):
    _attr_name = "Inactive turbines"
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_icon = "mdi:wind-turbine-alert"

    def __init__(self, coordinator, entry):
        super().__init__(coordinator, entry, "farm_inactive_turbines")

    @property
    def native_value(self):
        return self.coordinator.data[SCOPE_OWNER]["summary"].get("inactive_turbines")


class TurbinePowerSensor(KirkHillScopedTurbineEntity, SensorEntity):
    _attr_device_class = SensorDeviceClass.POWER
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_native_unit_of_measurement = UnitOfPower.KILO_WATT

    def __init__(self, coordinator, entry, turbine_id: str, scope: str):
        super().__init__(coordinator, entry, turbine_id, scope, "power")
        self._attr_name = f"Power ({scope})"

    @property
    def native_value(self):
        t = self._turbine_data(self._scope)
        return t.get("power_kw") if t else None


class TurbineCapacityFactorSensor(KirkHillScopedTurbineEntity, SensorEntity):
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_native_unit_of_measurement = PERCENTAGE
    _attr_icon = "mdi:gauge"

    def __init__(self, coordinator, entry, turbine_id: str, scope: str):
        super().__init__(coordinator, entry, turbine_id, scope, "capacity_factor")
        self._attr_name = f"Capacity factor ({scope})"

    @property
    def native_value(self):
        t = self._turbine_data(self._scope)
        return t.get("capacity_factor_percent") if t else None


class TurbineWindSpeedSensor(KirkHillTurbineEntity, SensorEntity):
    _attr_name = "Wind speed"
    _attr_device_class = SensorDeviceClass.WIND_SPEED
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_native_unit_of_measurement = UnitOfSpeed.METERS_PER_SECOND

    def __init__(self, coordinator, entry, turbine_id: str):
        super().__init__(coordinator, entry, turbine_id, "wind_speed")

    @property
    def native_value(self):
        t = self._turbine_data(SCOPE_OWNER)
        return t.get("wind_speed_mps") if t else None


class TurbineStateSensor(KirkHillTurbineEntity, SensorEntity):
    _attr_name = "State"
    _attr_icon = "mdi:information-outline"

    def __init__(self, coordinator, entry, turbine_id: str):
        super().__init__(coordinator, entry, turbine_id, "state_text")

    @property
    def native_value(self):
        t = self._turbine_data(SCOPE_OWNER)
        return t.get("state_text") if t else None

    @property
    def extra_state_attributes(self) -> dict:
        t = self._turbine_data(SCOPE_OWNER)
        if t is None:
            return {}
        coords = self.coordinator.data.get("coordinates", {}).get(self._turbine_id, {})
        return {
            "status": t.get("status"),
            "status_started_at": t.get("status_started_at"),
            "state_started_at": t.get("state_started_at"),
            "latitude": coords.get("latitude"),
            "longitude": coords.get("longitude"),
            "location_source": coords.get("source"),
            "openstreetmap_node_id": coords.get("openstreetmap_node_id"),
        }
