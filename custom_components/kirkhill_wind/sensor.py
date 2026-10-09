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
from homeassistant.util import dt as dt_util

from .const import (
    SCOPE_OWNER,
    SCOPE_SITE,
    SCOPES,
    TIMEFRAME_ORDER,
    yearly_timeframes,
)
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


def _timeframe_label(timeframe: str) -> str:
    """Return a human-readable label for a timeframe key.

    Past-year keys like 'year_2024' become 'Generation (2024)' without
    requiring hard-coded entries for every year.
    """
    if timeframe.startswith("year_"):
        return f"Generation ({timeframe[5:]})"
    return TIMEFRAME_LABELS.get(timeframe, f"Generation ({timeframe})")


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


def _summary_kwh(summary) -> float | None:
    """Return a timeframe summary's generation in kWh, or None if it has none.

    One place for the ``total_generation_kwh`` -> ``total_kwh`` lookup that the
    All time sum, its components and the per-timeframe readers all repeat.
    Everywhere compares against ``None``: 0.0 is a real reading, not a gap.
    """
    if not isinstance(summary, dict):
        return None
    value = _as_float(summary.get("total_generation_kwh"))
    if value is not None:
        return value
    return _as_float(summary.get("total_kwh"))


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

    turbine_ids = [
        t.get("id")
        for t in coordinator.data[SCOPE_OWNER].get("turbines", [])
        if t.get("id") is not None
    ]

    # Every fixed timeframe plus one frame per past calendar year (year_YYYY).
    # Past years are derived so their sensors appear automatically as years
    # complete; they feed the All time sum but are not shown on the SCADA card.
    generation_timeframes = TIMEFRAME_ORDER + yearly_timeframes()

    entities: list = [
        *[FarmPowerSensor(coordinator, entry, scope) for scope in SCOPES],
        *[FarmCapacityFactorSensor(coordinator, entry, scope) for scope in SCOPES],
        FarmOwnerShareSensor(coordinator, entry),
        *[
            FarmGenerationByTimeframeSensor(coordinator, entry, scope, timeframe)
            for scope in SCOPES
            for timeframe in generation_timeframes
        ],
        *[
            GenerationValueByTimeframeSensor(coordinator, entry, scope, timeframe)
            for timeframe in generation_timeframes
            for scope in SCOPES
        ],
        MemberSavingsValueSensor(coordinator, entry),
        FarmWindSpeedSensor(coordinator, entry),
        OpenMeteoForecastWindSpeedSensor(
            coordinator,
            entry,
            "next_hour_wind_speed_mps",
            "Open-Meteo forecast wind (next hour)",
        ),
        OpenMeteoForecastWindSpeedSensor(
            coordinator,
            entry,
            "next_3h_avg_wind_speed_mps",
            "Open-Meteo forecast wind (next 3h avg)",
        ),
        OpenMeteoForecastWindSpeedSensor(
            coordinator,
            entry,
            "next_24h_avg_wind_speed_mps",
            "Open-Meteo forecast wind (next 24h avg)",
        ),
        FarmActiveTurbinesSensor(coordinator, entry),
        FarmInactiveTurbinesSensor(coordinator, entry),
        DataGeneratedAtSensor(coordinator, entry),
        UnknownTurbinesSensor(coordinator, entry),
        LatestImportStatusSensor(coordinator, entry),
    ]

    for tid in turbine_ids:
        entities += [
            TurbinePowerSensor(coordinator, entry, tid, scope) for scope in SCOPES
        ]
        entities += [
            TurbineCapacityFactorSensor(coordinator, entry, tid, scope)
            for scope in SCOPES
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
                site_summary = self.coordinator.data.get(SCOPE_SITE, {}).get(
                    "summary", {}
                )
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

    @property
    def extra_state_attributes(self) -> dict:
        attrs = super().extra_state_attributes
        attrs["data_stale"] = self._current_is_stale()
        return attrs


class FarmOwnerShareSensor(KirkHillScopedEntity, SensorEntity):
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_native_unit_of_measurement = PERCENTAGE
    _attr_icon = "mdi:account-cash"
    _attr_suggested_display_precision = 4

    def __init__(self, coordinator, entry):
        super().__init__(coordinator, entry, SCOPE_OWNER, "farm_owner_share")
        self._attr_name = "Owner share"

    @property
    def native_value(self):
        return self._owner_share_pct()


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
        return _as_float(
            self._scope_data().get("summary", {}).get("capacity_factor_percent")
        )

    @property
    def extra_state_attributes(self) -> dict:
        attrs = super().extra_state_attributes
        attrs["data_stale"] = self._summary_is_stale("today")
        return attrs


class FarmGenerationByTimeframeSensor(
    KirkHillScopedEntity, SensorEntity, RestoreEntity
):
    _attr_device_class = SensorDeviceClass.ENERGY
    _attr_state_class = SensorStateClass.TOTAL
    _attr_native_unit_of_measurement = UnitOfEnergy.KILO_WATT_HOUR
    _attr_suggested_display_precision = 2
    _attr_should_poll = False

    def __init__(self, coordinator, entry, scope: str, timeframe: str):
        super().__init__(coordinator, entry, scope, f"farm_generation_{timeframe}")
        self._timeframe = timeframe
        scope_label = scope.capitalize()
        label = _timeframe_label(timeframe)
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

    def _expected_year_frames(self) -> tuple[str, ...]:
        """Year frames the All time figure is built from.

        The current year (``year``) plus every completed year (``year_YYYY``),
        derived so future years join the sum automatically as they complete.
        """
        return ("year", *yearly_timeframes())

    def _missing_year_frames(self) -> list[str]:
        """Expected year frames the coordinator holds no usable value for.

        A frame whose fetch failed arrives as ``{}`` -- the coordinator keeps
        last-known summaries only on success -- and then sits in retry backoff
        for up to an hour. "Missing" therefore means "in backoff or not fetched
        yet", never "that year generated nothing".
        """
        summaries = self.coordinator.data.get("timeframe_summaries", {}).get(
            self._scope, {}
        )
        return [
            key
            for key in self._expected_year_frames()
            if _summary_kwh(summaries.get(key)) is None
        ]

    def _sum_yearly_kwh(self) -> float | None:
        """Sum the per-year timeframes so All time is built from its parts.

        All time is the sum of the current ``year`` frame plus every
        ``year_YYYY`` frame, so 2024 + 2025 + ... + the current year to date
        always equals the All time figure.

        An incomplete sum is not a sum. A year whose fetch failed used to be
        skipped silently, which understated All time by that whole year (2024
        alone is 25% of it, the current year 35%) while the attribute still
        claimed ``sum_of_years``. Returning None hands the decision to
        ``_live_kwh``, which falls back to the API's own ``range=all`` figure
        -- about 0.1% low, because that window trails the latest import -- and
        the attributes then name the missing frames.
        """
        summaries = self.coordinator.data.get("timeframe_summaries", {}).get(
            self._scope, {}
        )
        total = 0.0
        for key in self._expected_year_frames():
            value = _summary_kwh(summaries.get(key))
            if value is None:
                return None
            total += value
        return round(total, 3)

    def _live_kwh(self) -> float | None:
        """Return the live API value for this timeframe, or None if not yet available."""
        if self._timeframe == "alltime":
            # All time is the sum of the per-year figures (see _sum_yearly_kwh).
            summed = self._sum_yearly_kwh()
            if summed is not None:
                return summed
            # The per-year frames are absent or incomplete -- not fetched yet,
            # or a fetch failed and is sitting in retry backoff. Fall through
            # to the API's own range=all value: it trails the latest import by
            # about 0.1%, where a partial sum would be short by a whole year
            # (25-40%), and the row is never blank on the first poll either.
        summary = (
            self.coordinator.data.get("timeframe_summaries", {})
            .get(self._scope, {})
            .get(self._timeframe, {})
        )
        value = _summary_kwh(summary)
        if value is not None:
            return value

        # For owner scope, fall back to calculating from site data using owner share %
        if self._scope == SCOPE_OWNER:
            site_summary = (
                self.coordinator.data.get("timeframe_summaries", {})
                .get(SCOPE_SITE, {})
                .get(self._timeframe, {})
            )
            site_value = _summary_kwh(site_summary)
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
        stale = self._summary_is_stale(self._timeframe)
        if live is not None:
            display_unit, display_value = _display_energy_from_kwh(live)
            attrs["timeframe"] = self._timeframe
            attrs["generation_source"] = "stale" if stale else "api_dynamic"
            attrs["raw_generation_kwh"] = live
            attrs["display_unit"] = display_unit
            attrs["display_value"] = display_value
            if self._timeframe == "alltime":
                # Normally the sum of the per-year figures. When a year frame
                # is missing the value above is the API's range=all figure
                # instead (see _sum_yearly_kwh), so say which of the two it is
                # rather than claiming an incomplete sum.
                missing = self._missing_year_frames()
                if missing:
                    attrs["generation_source"] = "api_alltime_missing_years"
                    attrs["missing_year_frames"] = missing
                else:
                    attrs["generation_source"] = "sum_of_years"
                attrs["sum_of_years_kwh"] = self._yearly_components()
        elif self._restored_attrs:
            # Use restored attributes if available
            attrs.update(self._restored_attrs)
            attrs["generation_source"] = "restored"
        attrs["data_stale"] = stale
        return attrs

    def _yearly_components(self) -> dict[str, float]:
        """Return the per-year kWh figures that make up the All time sum.

        Missing frames are simply absent here; ``missing_year_frames`` in the
        attributes is what says so.
        """
        summaries = self.coordinator.data.get("timeframe_summaries", {}).get(
            self._scope, {}
        )
        components: dict[str, float] = {}
        for key in self._expected_year_frames():
            value = _summary_kwh(summaries.get(key))
            if value is None:
                continue
            label = key[5:] if key.startswith("year_") else "current"
            components[label] = value
        return components


class GenerationValueByTimeframeSensor(KirkHillScopedEntity, SensorEntity):
    _attr_device_class = SensorDeviceClass.MONETARY
    _attr_state_class = SensorStateClass.TOTAL
    _attr_native_unit_of_measurement = "GBP"
    _attr_suggested_display_precision = 2
    _attr_icon = "mdi:cash"

    def __init__(self, coordinator, entry, scope: str, timeframe: str):
        super().__init__(
            coordinator, entry, scope, f"farm_generation_value_{timeframe}"
        )
        self._timeframe = timeframe
        scope_label = scope.capitalize()
        label = _timeframe_label(timeframe)
        self._attr_name = f"{label} projected value ({scope_label})"

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

    @property
    def native_value(self):
        """Return earnings: live generation × scope price, else £0.00.

        Owner earnings use the owner price in pence/kWh; site earnings use the
        negotiated CfD price in GBP/MWh. A price of 0.0 means none is
        configured yet — the sensor reads £0.00 rather than presenting a
        made-up projected figure, so no "stuck" static value shows on
        dashboards until a real price is set.

        The alltime timeframe is the exception: it returns unknown (the card
        shows "—") because the API only ever records energy, never money.
        Revaluing the farm's entire history at whatever price is set today is
        only valid while that price has never changed, so we suppress it until
        a real price history exists. The kWh energy figure is unaffected.
        """
        if self._timeframe == "alltime" or self._timeframe.startswith("year_"):
            return None
        kwh = self._live_kwh_for_timeframe()
        if kwh is None:
            return 0.0
        if self._scope == SCOPE_OWNER:
            price = getattr(self.coordinator, "owner_price_pence_per_kwh", 0.0)
            if price:
                return round(kwh * price / 100, 2)
            return 0.0
        price = getattr(self.coordinator, "negotiated_price_gbp_per_mwh", 0.0)
        if price:
            return round(kwh / 1000 * price, 2)
        return 0.0

    def _live_kwh_for_timeframe(self) -> float | None:
        """Live generation for this timeframe and scope, in kWh.

        Mirrors FarmGenerationByTimeframeSensor._live_kwh, minus the alltime
        sum (money is suppressed for alltime anyway). The owner fallback is
        load-bearing: without it the owner scope could show a derived kWh on
        the energy sensor while this one returned None -- and so £0.00 next to
        a configured price, while the attributes still reported
        projection_basis=live_owner_price_pence_per_kwh.
        """
        summary = (
            self.coordinator.data.get("timeframe_summaries", {})
            .get(self._scope, {})
            .get(self._timeframe, {})
        )
        value = _summary_kwh(summary)
        if value is not None:
            return value

        # The same fallback the energy sensor applies: derive the owner figure
        # from the site figure and the owner share when the owner scope has none.
        if self._scope == SCOPE_OWNER:
            site_summary = (
                self.coordinator.data.get("timeframe_summaries", {})
                .get(SCOPE_SITE, {})
                .get(self._timeframe, {})
            )
            site_value = _summary_kwh(site_summary)
            if site_value is not None:
                owner_share = self._owner_share_pct()
                if owner_share:
                    return round(site_value * owner_share / 100.0, 3)
        return None

    @property
    def extra_state_attributes(self) -> dict:
        attrs = super().extra_state_attributes
        attrs["timeframe"] = self._timeframe
        if self._timeframe == "alltime" or self._timeframe.startswith("year_"):
            attrs["projection_basis"] = "suppressed_no_historical_price"
            start_date = self._alltime_start_date()
            attrs["alltime_start_date"] = (
                start_date.isoformat() if start_date is not None else None
            )
            attrs["alltime_factor_source"] = (
                "api_timeframe_start"
                if start_date is not None
                else "legacy_fixed_20y_fallback"
            )
            return attrs
        if self._scope == SCOPE_OWNER:
            price = getattr(self.coordinator, "owner_price_pence_per_kwh", 0.0)
            attrs["projection_basis"] = (
                "live_owner_price_pence_per_kwh" if price else "no_owner_price_zero"
            )
        else:
            price = getattr(self.coordinator, "negotiated_price_gbp_per_mwh", 0.0)
            attrs["projection_basis"] = (
                "live_generation_x_price" if price else "no_price_zero"
            )
        return attrs


class MemberSavingsValueSensor(KirkHillScopedEntity, SensorEntity):
    """Capacity-based member savings: owned watts x the declared p/W rate.

    A different question from ``GenerationValueByTimeframeSensor``, which asks
    what your *generation* was worth at your p/kWh. Members are paid for the
    watts they *own*, and the period never enters the calculation: 1,000 W at
    a declared 20p/W is GBP 200 for whatever span the board declares.
    Generation takes no part in it, so this is unaffected by wind.

    There is deliberately no accrual. The board reviews its finances and
    declares a payment when it declares one, so until then no effective
    earning rate is knowable -- which is why the web dashboard shows no
    ongoing earnings at all. This entity holds the last declared rate and
    nothing more: no daily rate is derived, because none has ever been
    published. A yearly figure the board quotes is an equivalence for
    its declaration, not a rate to apply over time.

    No declared rate (``0.0``) returns ``None`` so the entity reads
    ``unknown`` -- asserting GBP 0.00 would be a figure the board never made.
    A *missing* capacity returns GBP 0.00 with
    ``projection_basis=no_capacity_zero`` instead: there is genuinely nothing
    to pay on, which is a different statement from "not yet declared".
    """

    _attr_device_class = SensorDeviceClass.MONETARY
    # TOTAL and not MEASUREMENT: HA allows only TOTAL for MONETARY
    # (homeassistant/components/sensor/const.py DEVICE_CLASS_STATE_CLASSES),
    # which is also what GenerationValueByTimeframeSensor uses.
    _attr_state_class = SensorStateClass.TOTAL
    _attr_native_unit_of_measurement = "GBP"
    _attr_suggested_display_precision = 2
    _attr_icon = "mdi:cash"

    def __init__(self, coordinator, entry):
        super().__init__(coordinator, entry, SCOPE_OWNER, "member_savings_value")
        self._attr_name = "Member savings value"

    @property
    def _owned_watts(self) -> float | None:
        """Owned capacity in watts from the owner scope's current summary."""
        data = self.coordinator.data.get(SCOPE_OWNER)
        summary = data.get("summary", {}) if isinstance(data, dict) else {}
        return _as_float(summary.get("capacity_watts"))

    @property
    def native_value(self):
        watts = self._owned_watts
        rate = getattr(self.coordinator, "owner_rate_pence_per_w", 0.0)
        if not watts:
            return 0.0
        if not rate:
            # Nothing declared yet: unknown, not zero. The payment is
            # retrospective, so "no rate" is an absence of information rather
            # than a statement that the payout is nil.
            return None
        return round(watts * rate / 100, 2)

    @property
    def extra_state_attributes(self) -> dict:
        attrs = super().extra_state_attributes
        watts = self._owned_watts
        rate = getattr(self.coordinator, "owner_rate_pence_per_w", 0.0)
        attrs["owned_watts"] = watts
        attrs["rate_pence_per_watt"] = rate
        if not watts:
            attrs["projection_basis"] = "no_capacity_zero"
        elif not rate:
            attrs["projection_basis"] = "no_rate_declared"
        else:
            attrs["projection_basis"] = "capacity_x_rate"
        attrs["data_stale"] = self._current_is_stale()
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
        summary = self.coordinator.data.get(SCOPE_OWNER, {}).get("summary", {})
        return _as_float(summary.get("wind_speed_mps"))


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
        value = self.coordinator.data.get("open_meteo_forecast", {}).get(
            self._forecast_key
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
        return (
            self.coordinator.data.get(SCOPE_OWNER, {})
            .get("summary", {})
            .get("active_turbines")
        )


class FarmInactiveTurbinesSensor(KirkHillEntity, SensorEntity):
    _attr_name = "Inactive turbines"
    _attr_icon = "mdi:wind-turbine-alert"
    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(self, coordinator, entry):
        super().__init__(coordinator, entry, "farm_inactive_turbines")

    @property
    def native_value(self):
        return (
            self.coordinator.data.get(SCOPE_OWNER, {})
            .get("summary", {})
            .get("inactive_turbines")
        )


class DataGeneratedAtSensor(KirkHillEntity, SensorEntity):
    """When the API response was generated (data freshness)."""

    _attr_name = "Data generated at"
    _attr_device_class = SensorDeviceClass.TIMESTAMP
    _attr_icon = "mdi:clock-check-outline"

    def __init__(self, coordinator, entry):
        super().__init__(coordinator, entry, "data_generated_at")

    @property
    def native_value(self):
        reading = self.coordinator.data.get(SCOPE_OWNER, {}).get("reading")
        if not isinstance(reading, dict):
            return None
        ts = reading.get("generated_at")
        if not isinstance(ts, str):
            return None
        return dt_util.parse_datetime(ts)


class UnknownTurbinesSensor(KirkHillEntity, SensorEntity):
    """Count of turbines with no imported state."""

    _attr_name = "Unknown turbines"
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_icon = "mdi:help-circle-outline"

    def __init__(self, coordinator, entry):
        super().__init__(coordinator, entry, "unknown_turbines")

    @property
    def native_value(self):
        return (
            self.coordinator.data.get(SCOPE_OWNER, {})
            .get("summary", {})
            .get("unknown_turbines")
        )


class LatestImportStatusSensor(KirkHillEntity, SensorEntity):
    """Status of the latest data import (e.g. 'completed')."""

    _attr_name = "Latest import status"
    _attr_icon = "mdi:import"

    def __init__(self, coordinator, entry):
        super().__init__(coordinator, entry, "latest_import_status")

    @property
    def native_value(self):
        summaries = self.coordinator.data.get("timeframe_summaries", {})
        today = summaries.get(SCOPE_OWNER, {}).get("today", {})
        return today.get("latest_import_status")

    @property
    def extra_state_attributes(self) -> dict:
        summaries = self.coordinator.data.get("timeframe_summaries", {})
        today = summaries.get(SCOPE_OWNER, {}).get("today", {})
        return {
            "latest_generation_interval_end": today.get(
                "latest_generation_interval_end"
            ),
        }


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
        if (
            self._restored_value is not None
            and data.get("generation_today_kwh") is None
        ):
            attrs["generation_source"] = "restored"
        return attrs


class TurbineGenerationAlltimeSensor(
    KirkHillTurbineEntity, SensorEntity, RestoreEntity
):
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
        if (
            self._restored_value is not None
            and data.get("generation_alltime_kwh") is None
        ):
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

    @property
    def extra_state_attributes(self) -> dict:
        return {"sampled_at": self._turbine_generation_data().get("rotor_speed_at")}
