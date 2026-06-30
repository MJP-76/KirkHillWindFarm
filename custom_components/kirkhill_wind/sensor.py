from homeassistant.components.sensor import (
    SensorEntity,
    SensorDeviceClass,
    SensorStateClass,
)
from homeassistant.const import UnitOfPower, UnitOfEnergy, PERCENTAGE
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.config_entries import ConfigEntry

from .coordinator import KirkHillCoordinator

async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Kirk Hill Wind Farm sensors based on a config entry."""
    # Retrieve your coordinator instance from hass.data (assigned during async_setup_entry in __init__.py)
    coordinator: KirkHillCoordinator = hass.data["kirkhill_wind"][entry.entry_id]

    # Define the sensors you want to map from your API data payload
    sensors = [
        KirkHillPowerSensor(coordinator),
        KirkHillEnergySensor(coordinator),
        KirkHillCapacitySensor(coordinator),
    ]

    async_add_entities(sensors, update_before_add=True)


class KirkHillBaseSensor(CoordinatorEntity, SensorEntity):
    """Base representation of a Kirk Hill Wind Farm Sensor."""

    def __init__(self, coordinator: KirkHillCoordinator) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator)
        # Link this sensor to a common device grouping in the UI
        self._attr_device_info = {
            "identifiers": {("kirkhill_wind", "cooperative_shares")},
            "name": "Kirk Hill Wind Farm",
            "manufacturer": "Ripple Energy",
        }


class KirkHillPowerSensor(KirkHillBaseSensor):
    """Sensor tracking current generation power output."""

    _attr_name = "Kirk Hill Current Generation"
    _attr_unique_id = "kirkhill_current_generation"
    _attr_device_class = SensorDeviceClass.POWER
    _attr_native_unit_of_measurement = UnitOfPower.WATT
    _attr_state_class = SensorStateClass.MEASUREMENT

    @property
    def native_value(self) -> float | None:
        """Return the state of the sensor."""
        # Grabs data securely out of the coordinator data dictionary
        return self.coordinator.data.get("current_generation")


class KirkHillEnergySensor(KirkHillBaseSensor):
    """Sensor tracking lifetime accumulated energy."""

    _attr_name = "Kirk Hill Total Generated"
    _attr_unique_id = "kirkhill_total_generated"
    _attr_device_class = SensorDeviceClass.ENERGY
    _attr_native_unit_of_measurement = UnitOfEnergy.KILOWATT_HOUR
    _attr_state_class = SensorStateClass.TOTAL_INCREASING

    @property
    def native_value(self) -> float | None:
        """Return the state of the sensor."""
        return self.coordinator.data.get("total_generated")


class KirkHillCapacitySensor(KirkHillBaseSensor):
    """Sensor tracking capacity factor performance percentage."""

    _attr_name = "Kirk Hill Capacity Factor"
    _attr_unique_id = "kirkhill_capacity_factor"
    _attr_native_unit_of_measurement = PERCENTAGE
    _attr_state_class = SensorStateClass.MEASUREMENT

    @property
    def native_value(self) -> float | None:
        """Return the state of the sensor."""
        return self.coordinator.data.get("capacity_factor")
