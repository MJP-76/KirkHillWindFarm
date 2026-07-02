import random
import time


class TurbineSim:
    """SCADA-style turbine model with physics + faults."""

    def __init__(self, turbine_id: int):
        self.id = turbine_id
        self.state = "normal"
        self.health = 100.0
        self.wind = random.uniform(6, 10)
        self.power = 0.0
        self.last_fault = 0

        # historian buffer
        self.history = []

    def step(self, global_wind: float):
        # ----------------------------
        # WIND INERTIA MODEL
        # ----------------------------
        self.wind += (global_wind - self.wind) * 0.08

        # ----------------------------
        # POWER CURVE (simplified real turbine model)
        # ----------------------------
        if self.wind < 3:
            self.power = 0
        elif self.wind < 12:
            self.power = (self.wind - 3) * 1.25
        else:
            self.power = 11.25  # rated cap

        # ----------------------------
        # HEALTH DYNAMICS
        # ----------------------------
        if self.state == "fault":
            self.health -= 0.6
        else:
            self.health += 0.05

        self.health = max(0, min(100, self.health))

        # ----------------------------
        # FAULT INJECTION (SCADA STYLE)
        # ----------------------------
        if random.random() < 0.002:
            self.state = "fault"
            self.last_fault = time.time()

        # ----------------------------
        # DEGRADATION RULE
        # ----------------------------
        if self.health < 25:
            self.state = "fault"
            self.last_fault = time.time()

        # ----------------------------
        # RECOVERY LOGIC (delayed)
        # ----------------------------
        if self.state == "fault":
            if time.time() - self.last_fault > 30:
                if random.random() < 0.12:
                    self.state = "normal"
                    self.health = 60

        # ----------------------------
        # HISTORY BUFFER (SCADA historian light)
        # ----------------------------
        self.history.append({
            "power": self.power,
            "wind": self.wind,
            "health": self.health,
        })

        if len(self.history) > 60:
            self.history.pop(0)

        return self.snapshot()

    def snapshot(self):
        return {
            "id": self.id,
            "state": self.state,
            "health": round(self.health, 1),
            "power_mw": round(self.power, 2),
            "wind_speed": round(self.wind, 2),
        }
