import logging
import random
from datetime import timedelta

from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from .const import DOMAIN, DEFAULT_SCAN_INTERVAL, TURBINE_COUNT
from .simulator import TurbineSim

_LOGGER = logging.getLogger(__name__)


class KirkHillWindCoordinator(DataUpdateCoordinator):
    """SCADA simulator coordinator (control loop engine)."""

    def __init__(self, hass, entry):
        self.hass = hass
        self.entry = entry

        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=timedelta(seconds=DEFAULT_SCAN_INTERVAL),
        )

        # ----------------------------
        # SCADA PLANT STATE
        # ----------------------------
        self.global_wind = 8.0
        self.turbines = [TurbineSim(i + 1) for i in range(TURBINE_COUNT)]

    async def _async_update_data(self):
        # ----------------------------
        # WIND FIELD DYNAMICS
        # ----------------------------
        self.global_wind += random.uniform(-0.3, 0.3)
        self.global_wind = max(0, min(25, self.global_wind))

        turbine_data = []
        faults = 0

        # ----------------------------
        # CONTROL LOOP EXECUTION
        # ----------------------------
        for t in self.turbines:
            snapshot = t.step(self.global_wind)
            turbine_data.append(snapshot)

            if snapshot["state"] == "fault":
                faults += 1

        # ----------------------------
        # FARM POWER
        # ----------------------------
        total_power = sum(t["power_mw"] for t in turbine_data)

        # ----------------------------
        # FARM STATE ENGINE
        # ----------------------------
        if faults >= 2:
            farm_state = "critical"
        elif faults == 1:
            farm_state = "degraded"
        else:
            farm_state = "normal"

        # ----------------------------
        # RETURN SCADA DATA MODEL
        # ----------------------------
        return {
            "farm": {
                "power_mw": round(total_power, 2),
                "wind_speed": round(self.global_wind, 2),
                "state": farm_state,
                "faults": faults,
            },
            "turbines": turbine_data,
        }
