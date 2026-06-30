from homeassistant.components.sensor import (
    SensorEntity,
    SensorDeviceClass,
    SensorStateClass,
)
from homeassistant.const import UnitOfEnergy, UnitOfPower, PERCENTAGE
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.config_entries import ConfigEntry

async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Kirk Hill Wind Farm sensors based on a config entry."""
    coordinator = hass.data["kirkhill_wind"][entry.entry_id]

    # Initialize all sensors mapped directly to your API's summary keys
    sensors = [
        KirkHillEnergySensor(coordinator),
        KirkHillCapacityFactorSensor(coordinator),
        KirkHillActiveTurbinesSensor(coordinator),
        KirkHillSiteCapacitySensor(coordinator),
    ]

    async_add_entities(sensors, update_before_add=True)


class KirkHillBaseSensor(CoordinatorEntity, SensorEntity):
    """Base representation of a Kirk Hill Wind Farm Sensor."""

    def __init__(self, coordinator) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator)
        self._attr_device_info = {
            "identifiers": {("kirkhill_wind", "cooperative_shares")},
            "name": "Kirk Hill Wind Farm",
            "manufacturer": "Ripple Energy",
        }


class KirkHillEnergySensor(KirkHillBaseSensor):
    """Tracks lifetime accumulated energy production."""

    _attr_name = "Kirk Hill Total Generation"
    _attr_unique_id = "kirkhill_total_generation"
    _attr_device_class = SensorDeviceClass.ENERGY
    _attr_native_unit_of_measurement = UnitOfEnergy.KILO_WATT_HOUR
    _attr_state_class = SensorStateClass.TOTAL_INCREASING

    @property
    def native_value(self) -> float | None:
        return self.coordinator.data.get("total_generation")

    @property
    def extra_state_attributes(self) -> dict | None:
        """Add the timestamp of the last generation interval data pull."""
        return {"latest_generation_interval_end": self.coordinator.data.get("latest_interval")}


class KirkHillCapacityFactorSensor(KirkHillBaseSensor):
    """Tracks capacity factor performance percentage."""

    _attr_name = "Kirk Hill Capacity Factor"
    _attr_unique_id = "kirkhill_capacity_factor"
    _attr_native_unit_of_measurement = PERCENTAGE
    _attr_state_class = SensorStateClass.MEASUREMENT

    @property
    def native_value(self) -> float | None:
        return self.coordinator.data.get("capacity_factor")


class KirkHillActiveTurbinesSensor(KirkHillBaseSensor):
    """Tracks the number of currently spinning/active turbines."""

    _attr_name = "Kirk Hill Active Turbines"
    _attr_unique_id = "kirkhill_active_turbines"
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_icon = "mdi:wind-turbine"

    @property
    def native_value(self) -> int | None:
        return self.coordinator.data.get("active_turbines")


class KirkHillSiteCapacitySensor(KirkHillBaseSensor):
    """Tracks overall operational capacity footprint."""

    _attr_name = "Kirk Hill Site Capacity"
    _attr_unique_id = "kirkhill_site_capacity"
    _attr_device_class = SensorDeviceClass.POWER
    _attr_native_unit_of_measurement = UnitOfPower.WATT
    _attr_state_class = SensorStateClass.MEASUREMENT

    @property
    def native_value(self) -> int | None:
        return self.coordinator.data.get("site_capacity_watts")
