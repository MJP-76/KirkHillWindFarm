"""Number platform for user-adjustable Kirk Hill figures.

These appear in the integration's entity list so users can fine-tune the price
values live instead of reconfiguring the integration.  Changes are persisted to
the config entry options so they survive restarts without relying solely on
RestoreEntity.

RestoreEntity is retained as a *one-time backfill*, not as a source of truth.
See ``_PriceBackfillMixin`` and AGENTS.md rule 3.
"""

from __future__ import annotations

from homeassistant.components.number import NumberEntity, NumberMode
from homeassistant.helpers.restore_state import RestoreEntity

from .const import (
    CONF_CFD_PRICE_GBP_PER_MWH,
    CONF_OWNER_PRICE_PENCE_PER_KWH,
    CONF_OWNER_RATE_PENCE_PER_W,
    CONF_PRICE_RESTORE_PENDING,
)
from .entity import KirkHillEntity
from .settings import merge_options


async def async_setup_entry(hass, entry, async_add_entities):
    """Set up the user-adjustable number entities."""
    coordinator = entry.runtime_data
    async_add_entities(
        [
            NegotiatedPriceNumber(coordinator, entry),
            OwnerPriceNumber(coordinator, entry),
            OwnerRateNumber(coordinator, entry),
        ]
    )


class _PriceBackfillMixin:
    """One-time recovery of prices that predate options-based persistence.

    History: until v4.13.0 these entities wrote nowhere, so a price the user
    set before then existed only in ``restore_state``. The v5/v6 migrations
    could not recover it -- they seeded the declared default into options --
    so ``entry.options`` cannot distinguish "never set" from "set before
    persistence existed".

    The v9 migration records the affected keys in
    ``CONF_PRICE_RESTORE_PENDING``. This mixin consumes that marker exactly
    once per key:

    * marker absent -> options is authoritative, restore_state is never read.
      This is the steady state, and it is what stops a stale restore record
      from overwriting a price the user has since changed.
    * marker present and containing this entity's key -> read restore_state,
      persist the recovered value, drop the key from the marker.

    Two entities share one entry, so the marker holds a *list*: a single
    shared boolean would let whichever entity set up first clear it, silently
    stranding the other's price. Each entity removes only its own key, and the
    marker is deleted once the list empties.
    """

    _price_key: str
    _price_attr: str

    async def _async_backfill_price(self) -> None:
        """Recover this price from restore_state if the migration flagged it."""
        # Read the current options rather than trusting a value cached at
        # __init__: the sibling entity may have already written its result.
        options = dict(self._entry.options)

        pending = options.get(CONF_PRICE_RESTORE_PENDING) or ()
        if self._price_key not in pending:
            return

        remaining = [key for key in pending if key != self._price_key]

        last_state = await self.async_get_last_state()
        if last_state is not None and last_state.state:
            try:
                restored = float(last_state.state)
            except (TypeError, ValueError):
                restored = None
            if restored is not None:
                options[self._price_key] = restored
                setattr(self.coordinator, self._price_attr, restored)
                # No async_write_ha_state() here: EntityPlatform writes state
                # immediately after this coroutine returns, so the recovered
                # value is published by that write. Calling it now would be a
                # redundant write, and errors on a not-yet-registered entity.

        # merge_options rather than a bare literal: HA replaces options
        # wholesale, so a partial write would drop every other setting.
        merged = merge_options(dict(self._entry.options), options)

        # merge_options is a spread, so it can only add or overwrite keys --
        # never remove one. The marker has to be deleted from the merged result
        # once the last price is done, or it survives into the steady state and
        # a stale restore record can overwrite a price on some later restart.
        if remaining:
            merged[CONF_PRICE_RESTORE_PENDING] = remaining
        else:
            merged.pop(CONF_PRICE_RESTORE_PENDING, None)

        self.hass.config_entries.async_update_entry(
            self._entry,
            options=merged,
        )


class NegotiatedPriceNumber(
    _PriceBackfillMixin, KirkHillEntity, RestoreEntity, NumberEntity
):
    """A user-editable negotiated CfD price in GBP per MWh."""

    _price_key = CONF_CFD_PRICE_GBP_PER_MWH
    _price_attr = "negotiated_price_gbp_per_mwh"

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
        # merge_options keeps every other setting; a plain dict literal here
        # would drop them, because Home Assistant replaces options wholesale.
        self.hass.config_entries.async_update_entry(
            self._entry,
            options=merge_options(
                dict(self._entry.options),
                {CONF_CFD_PRICE_GBP_PER_MWH: float(value)},
            ),
        )
        self.async_write_ha_state()

    async def async_added_to_hass(self) -> None:
        """One-time backfill of a pre-v4.13.0 price; see _PriceBackfillMixin."""
        await super().async_added_to_hass()
        await self._async_backfill_price()


class OwnerPriceNumber(
    _PriceBackfillMixin, KirkHillEntity, RestoreEntity, NumberEntity
):
    """A user-editable owner price in pence per kWh."""

    _price_key = CONF_OWNER_PRICE_PENCE_PER_KWH
    _price_attr = "owner_price_pence_per_kwh"

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
            options=merge_options(
                dict(self._entry.options),
                {CONF_OWNER_PRICE_PENCE_PER_KWH: float(value)},
            ),
        )
        self.async_write_ha_state()

    async def async_added_to_hass(self) -> None:
        """One-time backfill of a pre-v4.13.0 price; see _PriceBackfillMixin."""
        await super().async_added_to_hass()
        await self._async_backfill_price()


class OwnerRateNumber(KirkHillEntity, NumberEntity):
    """A user-editable member savings rate in pence per owned watt.

    Unlike the two prices above, this key is new -- there has never been a
    pre-persistence value for it to recover -- so it deliberately carries no
    ``RestoreEntity``/``_PriceBackfillMixin`` path: ``entry.options`` is its
    only source of truth from its first release. See AGENTS.md rule 3 before
    adding one.

    The rate is a declared figure, not a standing price. Members are paid for
    the watts they own and the period never enters the calculation ("time
    frame doesn't come into the calculation at all" -- 1,000 W at 21p/W is
    GBP 210 for whatever span the board declares). The board reviews its
    finances and declares a payment when it declares one, so this entity
    holds the latest declaration, and ``0.0`` means nothing has been
    declared -- the value sensor then reads ``unknown`` rather than a figure
    the board never promised.
    """

    _attr_native_unit_of_measurement = "p/W"
    _attr_mode = NumberMode.BOX
    _attr_native_min_value = 0.0
    _attr_native_max_value = 100.0
    _attr_native_step = 0.1
    _attr_icon = "mdi:cash-sync"

    def __init__(self, coordinator, entry):
        super().__init__(coordinator, entry, "owner_rate_pence_per_w")
        self._attr_name = "Owner rate (p/W)"

    @property
    def native_value(self) -> float | None:
        return getattr(self.coordinator, "owner_rate_pence_per_w", 0.0)

    async def async_set_native_value(self, value) -> None:
        self.coordinator.owner_rate_pence_per_w = float(value)
        # Persist to config entry options so the value survives restarts.
        # merge_options keeps every other setting; a plain dict literal here
        # would drop them, because Home Assistant replaces options wholesale.
        self.hass.config_entries.async_update_entry(
            self._entry,
            options=merge_options(
                dict(self._entry.options),
                {CONF_OWNER_RATE_PENCE_PER_W: float(value)},
            ),
        )
        self.async_write_ha_state()
