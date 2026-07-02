"""Sensor platform for Kirkhill Coop Wind Farm."""
import logging
from homeassistant.components.sensor import (
    SensorEntity,
    SensorDeviceClass,
    SensorStateClass,
    SensorEntityDescription,
)
from homeassistant.const import UnitOfPower, UnitOfEnergy, UnitOfSpeed
from homeassistant.helpers.update_coordinator import CoordinatorEntity

_LOGGER = logging.getLogger(__name__)

async def async_setup_entry(hass, entry, async_add_entities):
    """Set up Kirk Hill sensors based on config entry."""
    coordinator = hass.data["kirkhill_wind"][entry.entry_id]
    entities = []

    # 1. SITE-SCOPED ENTITIES
    site_sensors = [
        SensorEntityDescription(
            key="power",
            name="Site Power Generation",
            native_unit_of_measurement=UnitOfPower.KILOWATT,
            device_class=SensorDeviceClass.POWER,
            state_class=SensorStateClass.MEASUREMENT,
        ),
        SensorEntityDescription(
            key="speed",
            name="Wind Speed",
            native_unit_of_measurement=UnitOfSpeed.METERS_PER_SECOND,
            device_class=SensorDeviceClass.WIND_SPEED,
            state_class=SensorStateClass.MEASUREMENT,
        ),
        SensorEntityDescription(
            key="capacity_factor",
            name="Capacity Factor",
            native_unit_of_measurement="%",
            state_class=SensorStateClass.MEASUREMENT,
        ),
    ]
    
    for desc in site_sensors:
        # Match descriptions to API dictionary keys
        bucket = "wind" if "speed" in desc.key else "current"
        entities.append(KirkHillSensor(coordinator, desc, scope="site", api_bucket=bucket))

    # 2. OWNER-SCOPED ENTITIES
    owner_sensors = [
        SensorEntityDescription(
            key="power",
            name="My Share Power",
            native_unit_of_measurement=UnitOfPower.KILOWATT,
            device_class=SensorDeviceClass.POWER,
            state_class=SensorStateClass.MEASUREMENT,
        ),
        SensorEntityDescription(
            key="total_generation",
            name="My Total Energy Generation",
            native_unit_of_measurement=UnitOfEnergy.KILOWATT_HOUR,
            device_class=SensorDeviceClass.ENERGY,
            state_class=SensorStateClass.TOTAL_INCREASING,  # Enables full energy dashboard support
        ),
    ]

    for desc in owner_sensors:
        bucket = "generation" if "total" in desc.key else "current"
        entities.append(KirkHillSensor(coordinator, desc, scope="owner", api_bucket=bucket))

    # 3. DYNAMIC PER-TURBINE SENSORS (SITE SCOPE)
    site_turbines = coordinator.data.get("site", {}).get("turbines", {})
    if isinstance(site_turbines, dict):
        for turbine_id in site_turbines.keys():
            t_desc = SensorEntityDescription(
                key=turbine_id,
                name=f"Turbine {turbine_id} Output",
                native_unit_of_measurement=UnitOfPower.KILOWATT,
                device_class=SensorDeviceClass.POWER,
                state_class=SensorStateClass.MEASUREMENT,
            )
            entities.append(KirkHillSensor(coordinator, t_desc, scope="site", api_bucket="turbines"))

    async_add_entities(entities)


class KirkHillSensor(CoordinatorEntity, SensorEntity):
    """Representation of a generic KirkHill Wind Farm sensor."""

    def __init__(self, coordinator, description, scope: str, api_bucket: str):
        """Initialize the sensor."""
        super().__init__(coordinator)
        self.entity_description = description
        self._scope = scope          # "owner" or "site"
        self._api_bucket = api_bucket  # "current", "summary", "generation", "wind", "turbines"
        
        # Unique ID combining scope and entity key prevents overlap errors
        self._attr_unique_id = f"kirkhill_{scope}_{description.key}"
        
        # Creates separate clean cards for Site and Owner scopes in HA UI
        self._attr_device_info = {
            "identifiers": {("kirkhill_wind", scope)},
            "name": f"Kirk Hill Wind Farm ({scope.capitalize()} Scope)",
            "manufacturer": "KirkHill Coop",
        }

    @property
    def native_value(self):
        """Safely crawl the nested scope object based on the data roadmap."""
        if not self.coordinator.data:
            return None
            
        return (
            self.coordinator.data
            .get(self._scope, {})
            .get(self._api_bucket, {})
            .get(self.entity_description.key)
        )
