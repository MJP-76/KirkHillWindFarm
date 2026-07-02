from homeassistant.components.sensor import SensorEntity
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN


async def async_setup_entry(hass, entry, async_add_entities):
    coordinator = hass.data[DOMAIN][entry.entry_id]

    entities = [
        FarmPowerSensor(coordinator),
        FarmWindSensor(coordinator),
        FarmStateSensor(coordinator),
        FarmFaultSensor(coordinator),
    ]

    for i in range(len(coordinator.turbines)):
        entities.append(TurbineSensor(coordinator, i))

    async_add_entities(entities)


class BaseSensor(CoordinatorEntity, SensorEntity):
    def __init__(self, coordinator):
        super().__init__(coordinator)


# ----------------------------
# FARM SENSORS
# ----------------------------

class FarmPowerSensor(BaseSensor):
    @property
    def name(self):
        return "SCADA Farm Power"

    @property
    def unique_id(self):
        return f"{DOMAIN}_farm_power"

    @property
    def native_value(self):
        return self.coordinator.data["farm"]["power_mw"]

    @property
    def native_unit_of_measurement(self):
        return "MW"


class FarmWindSensor(BaseSensor):
    @property
    def name(self):
        return "SCADA Wind Speed"

    @property
    def unique_id(self):
        return f"{DOMAIN}_wind"

    @property
    def native_value(self):
        return self.coordinator.data["farm"]["wind_speed"]

    @property
    def native_unit_of_measurement(self):
        return "m/s"


class FarmStateSensor(BaseSensor):
    @property
    def name(self):
        return "SCADA Farm State"

    @property
    def unique_id(self):
        return f"{DOMAIN}_state"

    @property
    def native_value(self):
        return self.coordinator.data["farm"]["state"]


class FarmFaultSensor(BaseSensor):
    @property
    def name(self):
        return "SCADA Fault Count"

    @property
    def unique_id(self):
        return f"{DOMAIN}_faults"

    @property
    def native_value(self):
        return self.coordinator.data["farm"]["faults"]


# ----------------------------
# TURBINE SENSOR (SCADA TILE)
# ----------------------------

class TurbineSensor(BaseSensor):
    def __init__(self, coordinator, index):
        super().__init__(coordinator)
        self.index = index

    def turbine(self):
        return self.coordinator.data["turbines"][self.index]

    @property
    def name(self):
        return f"Turbine {self.index + 1} SCADA"

    @property
    def unique_id(self):
        return f"{DOMAIN}_t{self.index}"

    @property
    def native_value(self):
        t = self.turbine()
        return f"{t['state']} | {t['power_mw']} MW | {t['health']}%"
