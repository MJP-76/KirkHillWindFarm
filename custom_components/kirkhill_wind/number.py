"""Number platform for manually entered published-book finance figures."""
from __future__ import annotations

from homeassistant.components.number import NumberEntity, NumberMode, RestoreNumber

from .entity import KirkHillEntity

PUBLISHED_BOOK_FIELDS: tuple[tuple[str, str], ...] = (
    ("books_revenue_gbp", "Published books revenue"),
    ("books_operating_costs_gbp", "Published books operating costs"),
    ("books_finance_costs_gbp", "Published books finance costs"),
    ("books_other_costs_gbp", "Published books other costs"),
    ("books_owner_distribution_gbp", "Published books owner distribution"),
)


async def async_setup_entry(hass, entry, async_add_entities):
    """Set up editable finance numbers for the dashboard."""
    coordinator = entry.runtime_data
    entities = [
        PublishedBooksFigureNumber(coordinator, entry, unique_suffix, name)
        for unique_suffix, name in PUBLISHED_BOOK_FIELDS
    ]
    async_add_entities(entities)


class PublishedBooksFigureNumber(KirkHillEntity, RestoreNumber, NumberEntity):
    """A user-editable monetary figure from published financial books."""

    _attr_mode = NumberMode.BOX
    _attr_native_min_value = 0.0
    _attr_native_max_value = 1_000_000_000.0
    _attr_native_step = 1.0
    _attr_native_unit_of_measurement = "GBP"
    _attr_suggested_display_precision = 2
    _attr_icon = "mdi:currency-gbp"

    def __init__(self, coordinator, entry, unique_suffix: str, name: str) -> None:
        super().__init__(coordinator, entry, unique_suffix)
        self._attr_name = name
        self._attr_native_value = 0.0

    async def async_added_to_hass(self) -> None:
        """Restore the last persisted value after restarts/reloads."""
        await super().async_added_to_hass()
        last_number = await self.async_get_last_number_data()
        if last_number is not None:
            self._attr_native_value = last_number.native_value

    async def async_set_native_value(self, value: float) -> None:
        """Persist a new value set by the user."""
        self._attr_native_value = float(value)
        self.async_write_ha_state()
