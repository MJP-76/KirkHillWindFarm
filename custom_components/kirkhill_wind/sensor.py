"""Sensor platform for Kirk Hill Wind Farm integration."""
from __future__ import annotations

from typing import Any
from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import PERCENTAGE, UnitOfEnergy, UnitOfPower
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN

async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the sensor entities based on the active coordinator."""
    coordinator = hass.data[DOMAIN][config_entry.entry_id]

    sensors = [
        # --- Your Share (Owner) Metrics ---
        KirkhillOpenAPISensor(coordinator, "summary_owner", "total_generation_kwh", "Your Share Generation 7D", UnitOfEnergy.KILO_WATT_HOUR, "mdi:lightning-bolt", SensorDeviceClass.ENERGY, SensorStateClass.TOTAL),
        KirkhillOpenAPISensor(coordinator, "summary_owner", "capacity_factor_percent", "Your Share Capacity Factor", PERCENTAGE, "mdi:percent", None),

        # --- Whole Site Metrics ---
        KirkhillOpenAPISensor(coordinator, "summary_site", "total_generation_kwh", "Whole Site Generation 7D", UnitOfEnergy.KILO_WATT_HOUR, "mdi:lightning-bolt", SensorDeviceClass.ENERGY, SensorStateClass.TOTAL),
        KirkhillOpenAPISensor(coordinator, "summary_site", "capacity_factor_percent", "Whole Site Capacity Factor", PERCENTAGE, "mdi:percent", None),
        KirkhillOpenAPISensor(coordinator, "summary_site", "active_turbines", "Active Turbine Count", None, "mdi:wind-turbine", None),
        KirkhillOpenAPISensor(coordinator, "summary_site", "site_capacity_watts", "Site Total Capacity", UnitOfPower.WATT, "mdi:lightning-bolt", SensorDeviceClass.POWER),
    ]

    async_add_entities(sensors, update_before_add=False)


class KirkhillOpenAPISensor(CoordinatorEntity, SensorEntity):
    """Defines a sensor mapped to an explicit OpenAPI JSON schema parameter."""

    def __init__(
        self,
        coordinator,
        payload_block: str,
        json_key: str,
        friendly_name: str,
        unit: str | None,
        icon: str,
        device_class: SensorDeviceClass | None,
        state_class: SensorStateClass = SensorStateClass.MEASUREMENT
    ) -> None:
        """Initialize the OpenAPI data key properties."""
        super().__init__(coordinator)
        self._payload_block = payload_block
        self._json_key = json_key
        self._attr_name = f"Kirk Hill {friendly_name}"
        self._attr_unique_id = f"kirkhill_{payload_block}_{json_key}"
        self._attr_native_unit_of_measurement = unit
        self._attr_icon = icon
        self._attr_device_class = device_class
        self._attr_state_class = state_class

    @property
    def native_value(self) -> float | int | str | None:
        """Extract properties safely from the data -> summary nesting."""
        if not self.coordinator.data or self._payload_block not in self.coordinator.data:
            return None
        
        # Step into the top-level block entry dictionary
        block = self.coordinator.data[self._payload_block]
        if not isinstance(block, dict):
            return None

        # Safe extraction prevents crashes if the block is empty
        data_wrapper = block.get("data")
        if not isinstance(data_wrapper, dict):
            return None
            
        summary_block = data_wrapper.get("summary")
        if isinstance(summary_block, dict):
            return summary_block.get(self._json_key)
            
        return None
