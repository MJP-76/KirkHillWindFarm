from dataclasses import dataclass
from typing import Callable

from homeassistant.components.sensor import (
    SensorEntity,
    SensorEntityDescription,
    SensorDeviceClass,
    SensorStateClass,
)
from homeassistant.const import UnitOfEnergy, UnitOfPower, PERCENTAGE
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.update_coordinator import CoordinatorEntity

# 1. Create a custom description schema to link API keys to our sensors
@dataclass(frozen=True)
class KirkHillSensorEntityDescription(SensorEntityDescription):
    """Describes Kirk Hill Wind Farm sensor entity."""
    value_fn: Callable[[dict], any] = None


# 2. DEFINE ALL API SENSORS HERE IN ONE CLEAN LIST
SENSOR_TYPES: tuple[KirkHillSensorEntityDescription, ...] = (
    # --- Summary Dataset ---
    KirkHillSensorEntityDescription(
        key="total_generation",
        name="Kirk Hill Total Generation",
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL_INCREASING,
        value_fn=lambda data: data.get("total_generation"),
    ),
    KirkHillSensorEntityDescription(
        key="capacity_factor",
        name="Kirk Hill Capacity Factor",
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:percent",
        value_fn=lambda data: data.get("capacity_factor"),
    ),
    KirkHillSensorEntityDescription(
        key="active_turbines",
        name="Kirk Hill Active Turbines",
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:wind-turbine",
        value_fn=lambda data: data.get("active_turbines"),
    ),
    KirkHillSensorEntityDescription(
        key="site_capacity_watts",
        name="Kirk Hill Site Capacity",
        native_unit_of_measurement=UnitOfPower.WATT,
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda data: data.get("site_capacity_watts"),
    ),
    KirkHillSensorEntityDescription(
        key="latest_interval",
        name="Kirk Hill Latest Generation Interval End",
        device_class=SensorDeviceClass.TIMESTAMP,
        value_fn=lambda data: data.get("latest_interval"),
    ),
    KirkHillSensorEntityDescription(
        key="import_status",
        name="Kirk Hill Latest Import Status",
        icon="mdi:database-check",
        value_fn=lambda data: data.get("import_status"),
    ),
    
    # --- Window Dataset ---
    KirkHillSensorEntityDescription(
        key="range",
        name="Kirk Hill Data Window Range",
        icon="mdi:calendar-range",
        value_fn=lambda data: data.get("range"),
    ),
    KirkHillSensorEntityDescription(
        key="from_time",
        name="Kirk Hill Data Window From",
        device_class=SensorDeviceClass.TIMESTAMP,
        value_fn=lambda data: data.get("from_time"),
    ),
    KirkHillSensorEntityDescription(
        key="to_time",
        name="Kirk Hill Data Window To",
        device_class=SensorDeviceClass.TIMESTAMP,
        value_fn=lambda data: data.get("to_time"),
    ),
    KirkHillSensorEntityDescription(
        key="bucket",
        name="Kirk Hill Data Window Bucket",
        icon="mdi:clock-outline",
        value_fn=lambda data: data.get("bucket"),
    ),
    KirkHillSensorEntityDescription(
        key="scope",
        name="Kirk Hill API Token Scope",
        icon="mdi:account-lock",
        value_fn=lambda data: data.get("scope"),
    ),
    KirkHillSensorEntityDescription(
        key="timezone",
        name="Kirk Hill Site Timezone",
        icon="mdi:map-clock",
        value_fn=lambda data: data.get("timezone"),
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Kirk Hill Wind Farm sensors dynamically based on descriptions list."""
    coordinator = hass.data["kirkhill_wind"][entry.entry_id]

    # This loops through the list above and automatically builds all 12 sensors
    async_add_entities(
        [KirkHillSensor(coordinator, description) for description in SENSOR_TYPES],
        update_before_add=True
    )


# 3. SINGLE REUSABLE SENSOR CLASS WRAPPER
class KirkHillSensor(CoordinatorEntity, SensorEntity):
    """Representation of a dynamic Kirk Hill Wind Farm Sensor."""

    entity_description: KirkHillSensorEntityDescription

    def __init__(self, coordinator, description: KirkHillSensorEntityDescription) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator)
        self.entity_description = description
        
        # Unique ID prevents naming collisions inside Home Assistant core registries
        self._attr_unique_id = f"kirkhill_{description.key}"
        
        # Link this entity to the master wind farm device layout
        self._attr_device_info = {
            "identifiers": {("kirkhill_wind", "cooperative_shares")},
            "name": "Kirk Hill Wind Farm",
            "manufacturer": "Ripple Energy",
        }

    @property
    def native_value(self):
        """Return the state value using the template lambda function helper."""
        return self.entity_description.value_fn(self.coordinator.data)
