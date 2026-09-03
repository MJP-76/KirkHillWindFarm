"""Sensor platform for the Kirk Hill Wind Farm integration."""
from __future__ import annotations

from datetime import date, datetime, timezone

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.const import PERCENTAGE, UnitOfEnergy, UnitOfPower, UnitOfSpeed
from homeassistant.helpers.restore_state import RestoreEntity

from .const import (
    CONF_OWNER_PROJECTED_ANNUAL_EARNINGS_GBP,
    CONF_OWNER_SHARE_PERCENT,
    CONF_SITE_PROJECTED_ANNUAL_EARNINGS_GBP,
    DEFAULT_OWNER_PROJECTED_ANNUAL_EARNINGS_GBP,
    DEFAULT_SITE_PROJECTED_ANNUAL_EARNINGS_GBP,
    SCOPE_OWNER,
    SCOPE_SITE,
    SCOPES,
    TIMEFRAME_ORDER,
)
from .device import get_farm_device_id
from .entity import (
    KirkHillEntity,
    KirkHillScopedEntity,
    KirkHillScopedTurbineEntity,
    KirkHillTurbineEntity,
    turbine_status_category,
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


def _display_energy_from_kwh(value_kwh: float | None) -> tuple[str, float | None]:
    if value_kwh is None:
        return UnitOfEnergy.KILO_WATT_HOUR, None
    if value_kwh >= 1_000_000_000_000_000:
        return "EWh", round(value_kwh / 1_000_000_000_000_000, 2)
    if value_kwh >= 1_000_000_000_000:
        return "PWh", round(value_kwh / 1_000_000_000_000, 2)
    if value_kwh >= 1_000_000_000:
        return "TWh", round(value_kwh / 1_000_000_000, 2)
    if value_kwh >= 1_000_000:
        return "GWh", round(value_kwh / 1_000_000, 2)
    if value_kwh >= 1_000:
        return UnitOfEnergy.MEGA_WATT_HOUR, round(value_kwh / 1_000, 2)
    return UnitOfEnergy.KILO_WATT_HOUR, round(value_kwh, 2)


async def async_setup_entry(hass, entry, async_add_entities):
    coordinator = entry.runtime_data

    coordinator.farm_device_id = await get_farm_device_id(hass, entry)

    turbine_ids = [
        t.get("id")
        for t in coordinator.data[SCOPE_OWNER].get("turbines", [])
        if t.get("id") is not None
    ]

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
        entities.append(TurbineGenerationTodaySensor(coordinator, entry, tid))
        entities.append(TurbineGenerationAlltimeSensor(coordinator, entry, tid))
        entities.append(TurbineRotorSpeedSensor(coordinator, entry, tid))

    async_add_entities(entities)


class FarmPowerSensor(KirkHillScopedEntity, SensorEntity):
    _attr_device_class = SensorDeviceClass.POWER
    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(self, coordinator, entry, scope: str):
        super().__init__(coordinator, entry, scope, "farm_power")
        self._attr_name = f"Power ({scope.capitalize()})"
        self._attr_native_unit_of_measurement = (
            "MW" if scope == SCOPE_SITE else UnitOfPower.KILO_WATT
        )

    @property
    def native_value(self):
        scope_data = self._scope_data()
        summary = scope_data.get("summary", {}) if isinstance(scope_data, dict) else {}
        value = _as_float(summary.get("total_power_kw"))

        # For owner scope: if API returns 0/None, calculate from site power × owner share
        if self._scope == SCOPE_OWNER:
            if value is None or value == 0:
                site_summary = self.coordinator.data.get(SCOPE_SITE, {}).get("summary", {})
                site_power = _as_float(site_summary.get("total_power_kw"))
                if site_power is not None:
                    owner_share = self._owner_share_pct()
                    if owner_share and owner_share > 0:
                        return round(site_power * owner_share / 100.0, 3)
            return value

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
        self._attr_name = f"Capacity factor ({scope.capitalize()})"

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


class FarmGenerationByTimeframeSensor(KirkHillScopedEntity, SensorEntity, RestoreEntity):
    _attr_device_class = SensorDeviceClass.ENERGY
    _attr_state_class = SensorStateClass.TOTAL
    _attr_native_unit_of_measurement = UnitOfEnergy.KILO_WATT_HOUR
    _attr_suggested_display_precision = 2
    _attr_should_poll = False

    def __init__(self, coordinator, entry, scope: str, timeframe: str):
        super().__init__(coordinator, entry, scope, f"farm_generation_{timeframe}")
        self._timeframe = timeframe
        scope_label = scope.capitalize()
        label = TIMEFRAME_LABELS.get(timeframe, f"Generation ({timeframe})")
        self._attr_name = f"{label} ({scope_label})"
        self._restored_value: float | None = None
        self._restored_attrs: dict | None = None

    async def async_added_to_hass(self) -> None:
        """Restore last known state on startup."""
        await super().async_added_to_hass()
        last_state = await self.async_get_last_state()
        if last_state is not None:
            try:
                self._restored_value = float(last_state.state)
                self._restored_attrs = dict(last_state.attributes)
            except (ValueError, TypeError):
                self._restored_value = None
                self._restored_attrs = None

    def _live_kwh(self) -> float | None:
        """Return the live API value for this timeframe, or None if not yet available."""
        summary = (
            self.coordinator.data.get("timeframe_summaries", {})
            .get(self._scope, {})
            .get(self._timeframe, {})
        )
        value = _as_float(summary.get("total_generation_kwh"))
        if value is not None:
            return value
        value = _as_float(summary.get("total_kwh"))
        if value is not None:
            return value

        # For owner scope, fall back to calculating from site data using owner share %
        if self._scope == SCOPE_OWNER:
            site_summary = (
                self.coordinator.data.get("timeframe_summaries", {})
                .get(SCOPE_SITE, {})
                .get(self._timeframe, {})
            )
            site_value = _as_float(site_summary.get("total_generation_kwh"))
            if site_value is None:
                site_value = _as_float(site_summary.get("total_kwh"))
            if site_value is not None:
                owner_share = self._owner_share_pct()
                if owner_share:
                    return round(site_value * owner_share / 100.0, 3)

        return None

    def _generation_kwh(self) -> float | None:
        # Prefer live API data; only fall back to the restored value while
        # waiting for the first summary fetch after a restart (avoids "—" gaps).
        live = self._live_kwh()
        if live is not None:
            return live
        return self._restored_value

    @property
    def native_value(self):
        return self._generation_kwh()

    @property
    def extra_state_attributes(self) -> dict:
        attrs = super().extra_state_attributes
        live = self._live_kwh()
        if live is not None:
            display_unit, display_value = _display_energy_from_kwh(live)
            attrs["timeframe"] = self._timeframe
            attrs["generation_source"] = "api_dynamic"
            attrs["raw_generation_kwh"] = live
            attrs["display_unit"] = display_unit
            attrs["display_value"] = display_value
        elif self._restored_attrs:
            # Use restored attributes if available
            attrs.update(self._restored_attrs)
            attrs["generation_source"] = "restored"
        return attrs


class GenerationValueByTimeframeSensor(KirkHillScopedEntity, SensorEntity):
    _attr_device_class = SensorDeviceClass.MONETARY
    _attr_state_class = SensorStateClass.TOTAL
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

    @staticmethod
    def _parse_api_date(value) -> date | None:
        if isinstance(value, date) and not isinstance(value, datetime):
            return value
        if isinstance(value, datetime):
            return value.date()
        if isinstance(value, (int, float)):
            try:
                return datetime.fromtimestamp(float(value), tz=timezone.utc).date()
            except (OverflowError, OSError, ValueError):
                return None
        if isinstance(value, str):
            raw = value.strip()
            if not raw:
                return None
            normalized = raw.replace("Z", "+00:00")
            try:
                return datetime.fromisoformat(normalized).date()
            except ValueError:
                try:
                    return date.fromisoformat(raw)
                except ValueError:
                    return None
        return None

    def _alltime_start_date(self) -> date | None:
        summary = (
            self.coordinator.data.get("timeframe_summaries", {})
            .get(self._scope, {})
            .get("alltime", {})
        )
        if not isinstance(summary, dict):
            return None

        direct_keys = (
            "period_start",
            "range_start",
            "start_date",
            "start_at",
            "from_date",
            "from",
            "start",
            "since",
        )
        for key in direct_keys:
            if key in summary:
                parsed = self._parse_api_date(summary.get(key))
                if parsed is not None:
                    return parsed

        nested_keys = ("period", "range", "timeframe", "window")
        for container_key in nested_keys:
            nested = summary.get(container_key)
            if not isinstance(nested, dict):
                continue
            for key in ("start", "from", "start_date", "start_at"):
                parsed = self._parse_api_date(nested.get(key))
                if parsed is not None:
                    return parsed

        for key, value in summary.items():
            lowered = str(key).lower()
            if lowered == "from" or "start" in lowered:
                parsed = self._parse_api_date(value)
                if parsed is not None:
                    return parsed

        window = (
            self.coordinator.data.get("timeframe_windows", {})
            .get(self._scope, {})
            .get("alltime")
        )
        if isinstance(window, dict):
            for key in ("from", "start", "start_at", "start_date"):
                parsed = self._parse_api_date(window.get(key))
                if parsed is not None:
                    return parsed

        return None

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
            start_date = self._alltime_start_date()
            if start_date is None:
                return 20.0
            elapsed_days = max((date.today() - start_date).days, 1)
            return elapsed_days / 365
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
        if self._timeframe == "alltime":
            start_date = self._alltime_start_date()
            attrs["alltime_start_date"] = (
                start_date.isoformat() if start_date is not None else None
            )
            attrs["alltime_factor_source"] = (
                "api_timeframe_start" if start_date is not None else "legacy_fixed_20y_fallback"
            )
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
    _attr_icon = "mdi:wind-turbine"
    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(self, coordinator, entry):
        super().__init__(coordinator, entry, "farm_active_turbines")

    @property
    def native_value(self):
        return self.coordinator.data.get(SCOPE_OWNER, {}).get("summary", {}).get("active_turbines")

class FarmInactiveTurbinesSensor(KirkHillEntity, SensorEntity):
    _attr_name = "Inactive turbines"
    _attr_icon = "mdi:wind-turbine-alert"
    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(self, coordinator, entry):
        super().__init__(coordinator, entry, "farm_inactive_turbines")

    @property
    def native_value(self):
        return self.coordinator.data.get(SCOPE_OWNER, {}).get("summary", {}).get("inactive_turbines")

class TurbinePowerSensor(KirkHillScopedTurbineEntity, SensorEntity):
    _attr_device_class = SensorDeviceClass.POWER
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_native_unit_of_measurement = UnitOfPower.KILO_WATT

    def __init__(self, coordinator, entry, turbine_id: str, scope: str):
        super().__init__(coordinator, entry, turbine_id, scope, "power")
        self._attr_name = f"Power ({scope.capitalize()})"

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
        self._attr_name = f"Capacity factor ({scope.capitalize()})"

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
        state_text = t.get("state_text", "")
        return {
            "status": t.get("status"),
            "status_category": turbine_status_category(state_text),
            "status_started_at": t.get("status_started_at"),
            "state_started_at": t.get("state_started_at"),
            "latitude": coords.get("latitude"),
            "longitude": coords.get("longitude"),
            "location_source": coords.get("source"),
            "openstreetmap_node_id": coords.get("openstreetmap_node_id"),
        }


class TurbineGenerationTodaySensor(KirkHillTurbineEntity, SensorEntity, RestoreEntity):
    _attr_name = "Generation today"
    _attr_device_class = SensorDeviceClass.ENERGY
    _attr_state_class = SensorStateClass.TOTAL
    _attr_native_unit_of_measurement = UnitOfEnergy.KILO_WATT_HOUR
    _attr_icon = "mdi:chart-bar"
    _attr_should_poll = False

    def __init__(self, coordinator, entry, turbine_id: str):
        super().__init__(coordinator, entry, turbine_id, "generation_today")
        self._restored_value: float | None = None

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        last_state = await self.async_get_last_state()
        if last_state is not None:
            try:
                self._restored_value = float(last_state.state)
            except (ValueError, TypeError):
                self._restored_value = None

    @property
    def native_value(self):
        val = _as_float(self._turbine_generation_data().get("generation_today_kwh"))
        if val is not None:
            return val
        return self._restored_value

    @property
    def extra_state_attributes(self) -> dict:
        data = self._turbine_generation_data()
        attrs = {"share_percent": data.get("generation_today_share_percent")}
        if self._restored_value is not None and data.get("generation_today_kwh") is None:
            attrs["generation_source"] = "restored"
        return attrs


class TurbineGenerationAlltimeSensor(KirkHillTurbineEntity, SensorEntity, RestoreEntity):
    _attr_name = "Generation all-time"
    _attr_device_class = SensorDeviceClass.ENERGY
    _attr_state_class = SensorStateClass.TOTAL_INCREASING
    _attr_native_unit_of_measurement = UnitOfEnergy.KILO_WATT_HOUR
    _attr_icon = "mdi:chart-line"
    _attr_should_poll = False

    def __init__(self, coordinator, entry, turbine_id: str):
        super().__init__(coordinator, entry, turbine_id, "generation_alltime")
        self._restored_value: float | None = None

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        last_state = await self.async_get_last_state()
        if last_state is not None:
            try:
                self._restored_value = float(last_state.state)
            except (ValueError, TypeError):
                self._restored_value = None

    @property
    def native_value(self):
        val = _as_float(self._turbine_generation_data().get("generation_alltime_kwh"))
        if val is not None:
            return val
        return self._restored_value

    @property
    def extra_state_attributes(self) -> dict:
        data = self._turbine_generation_data()
        attrs = {"share_percent": data.get("generation_alltime_share_percent")}
        if self._restored_value is not None and data.get("generation_alltime_kwh") is None:
            attrs["generation_source"] = "restored"
        return attrs


class TurbineRotorSpeedSensor(KirkHillTurbineEntity, SensorEntity):
    _attr_name = "Rotor speed"
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_native_unit_of_measurement = "rpm"
    _attr_icon = "mdi:rotate-right"

    def __init__(self, coordinator, entry, turbine_id: str):
        super().__init__(coordinator, entry, turbine_id, "rotor_speed")

    @property
    def native_value(self):
        return _as_float(self._turbine_generation_data().get("rotor_speed_rpm"))
