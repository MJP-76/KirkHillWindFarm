"""Number platform for user-adjustable Kirk Hill figures.

These appear in the integration's entity list so users can fine-tune the price
values live instead of reconfiguring the integration.  Changes are persisted to
the config entry options so they survive restarts without relying solely on
RestoreEntity.
"""
from __future__ import annotations

from homeassistant.components.number import NumberDeviceClass, NumberEntity, NumberMode
from homeassistant.helpers.restore_state import RestoreEntity

from .const import CONF_CFD_PRICE_GBP_PER_MWH, CONF_OWNER_PRICE_PENCE_PER_KWH
from .entity import KirkHillEntity


async def async_setup_entry(hass, entry, async_add_entities):
    """Set up the user-adjustable number entities."""
    coordinator = entry.runtime_data
    async_add_entities(
        [
            NegotiatedPriceNumber(coordinator, entry),
            OwnerPriceNumber(coordinator, entry),
        ]
    )


class NegotiatedPriceNumber(KirkHillEntity, RestoreEntity, NumberEntity):
    """A user-editable negotiated CfD price in GBP per MWh."""

    _attr_native_unit_of_measurement = "GBP/MWh"
    _attr_mode = NumberMode.BOX
    _attr_native_min_value = 0.0
    _attr_native_max_value = 500.0
    _attr_native_step = 0.5
    _attr_icon = "mdi:cash-sync"

    def __init__(self, coordinator, entry):
        super().__init__(coordinator, entry, "negotiated_price_gbp_per_mwh")
        self._attr_name = "Negotiated price (GBP/MWh)"

    @property
    def native_value(self) -> float | None:
        return getattr(self.coordinator, "negotiated_price_gbp_per_mwh", 0.0)

    async def async_set_native_value(self, value) -> None:
        self.coordinator.negotiated_price_gbp_per_mwh = float(value)
        # Persist to config entry options so the value survives restarts.
        self.hass.config_entries.async_update_entry(
            self._entry,
            options={**self._entry.options, CONF_CFD_PRICE_GBP_PER_MWH: float(value)},
        )
        self.async_write_ha_state()

    async def async_added_to_hass(self) -> None:
        """Restore the user's last-edited value across restarts."""
        await super().async_added_to_hass()
        last_state = await self.async_get_last_state()
        if last_state is None:
            return
        try:
            value = float(last_state.state)
        except (TypeError, ValueError):
            return
        self.coordinator.negotiated_price_gbp_per_mwh = value


class OwnerPriceNumber(KirkHillEntity, RestoreEntity, NumberEntity):
    """A user-editable owner price in pence per kWh."""

    _attr_native_unit_of_measurement = "p/kWh"
    _attr_mode = NumberMode.BOX
    _attr_native_min_value = 0.0
    _attr_native_max_value = 50.0
    _attr_native_step = 0.1
    _attr_icon = "mdi:cash-sync"

    def __init__(self, coordinator, entry):
        super().__init__(coordinator, entry, "owner_price_pence_per_kwh")
        self._attr_name = "Owner price (p/kWh)"

    @property
    def native_value(self) -> float | None:
        return getattr(self.coordinator, "owner_price_pence_per_kwh", 0.0)

    async def async_set_native_value(self, value) -> None:
        self.coordinator.owner_price_pence_per_kwh = float(value)
        # Persist to config entry options so the value survives restarts.
        self.hass.config_entries.async_update_entry(
            self._entry,
            options={**self._entry.options, CONF_OWNER_PRICE_PENCE_PER_KWH: float(value)},
        )
        self.async_write_ha_state()

    async def async_added_to_hass(self) -> None:
        """Restore the user's last-edited value across restarts."""
        await super().async_added_to_hass()
        last_state = await self.async_get_last_state()
        if last_state is None:
            return
        try:
            value = float(last_state.state)
        except (TypeError, ValueError):
            return
        self.coordinator.owner_price_pence_per_kwh = value
