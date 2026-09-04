"""Number platform for user-adjustable Kirk Hill figures.

These appear in the integration's entity list so users can fine-tune the
projected-earnings values live instead of reconfiguring the integration.
"""
from __future__ import annotations

from homeassistant.components.number import NumberDeviceClass, NumberEntity, NumberMode
from homeassistant.helpers.restore_state import RestoreEntity

from .const import SCOPE_OWNER, SCOPE_SITE
from .entity import KirkHillEntity


async def async_setup_entry(hass, entry, async_add_entities):
    """Set up the user-adjustable number entities."""
    coordinator = entry.runtime_data
    async_add_entities(
        [
            ProjectedAnnualEarningsNumber(coordinator, entry, SCOPE_OWNER),
            ProjectedAnnualEarningsNumber(coordinator, entry, SCOPE_SITE),
        ]
    )


class ProjectedAnnualEarningsNumber(KirkHillEntity, RestoreEntity, NumberEntity):
    """A user-editable projected-annual-earnings figure (GBP)."""

    _attr_device_class = NumberDeviceClass.MONETARY
    _attr_native_unit_of_measurement = "GBP"
    _attr_mode = NumberMode.BOX
    _attr_native_min_value = 0.0
    _attr_native_max_value = 1000000.0
    _attr_native_step = 1.0
    _attr_icon = "mdi:cash"

    def __init__(self, coordinator, entry, scope: str):
        super().__init__(coordinator, entry, f"projected_annual_earnings_{scope}")
        self._scope = scope
        self._attr_name = f"Projected annual earnings ({scope.capitalize()})"

    @property
    def native_value(self) -> float | None:
        values = getattr(self.coordinator, "projected_annual_earnings_gbp", None)
        if values is None:
            return None
        return values.get(self._scope)

    async def async_set_native_value(self, value) -> None:
        values = getattr(self.coordinator, "projected_annual_earnings_gbp", None)
        if values is None:
            values = self.coordinator.projected_annual_earnings_gbp = {}
        values[self._scope] = float(value)
        self.async_write_ha_state()

    async def async_added_to_hass(self) -> None:
        """Restore the user's last-edited value across restarts.

        Falls back to the config seed already placed in
        coordinator.projected_annual_earnings_gbp by async_setup_entry.
        """
        await super().async_added_to_hass()
        last_state = await self.async_get_last_state()
        if last_state is None:
            return
        try:
            value = float(last_state.state)
        except (TypeError, ValueError):
            return
        values = getattr(self.coordinator, "projected_annual_earnings_gbp", None)
        if values is None:
            values = self.coordinator.projected_annual_earnings_gbp = {}
        values[self._scope] = value
