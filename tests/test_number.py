"""Tests for number entities — persistence to config entry options."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from homeassistant.helpers.restore_state import RestoreEntity

from custom_components.kirkhill_wind.const import (
    CONF_CFD_PRICE_GBP_PER_MWH,
    CONF_OWNER_PRICE_PENCE_PER_KWH,
    CONF_OWNER_RATE_PENCE_PER_W,
    CONF_PRICE_RESTORE_PENDING,
    CONF_SCAN_INTERVAL,
    CONF_SITE_NAME,
)
from custom_components.kirkhill_wind.number import (
    NegotiatedPriceNumber,
    OwnerPriceNumber,
    OwnerRateNumber,
)


class TestNumberPersistence:
    """Verify number entities persist changes to config entry options."""

    @pytest.mark.asyncio
    async def test_negotiated_price_persists_to_options(self):
        """Changing negotiated price should update config entry options."""
        coordinator = MagicMock()
        coordinator.negotiated_price_gbp_per_mwh = 50.0
        entry = MagicMock()
        entry.entry_id = "test"
        entry.options = {}

        hass = MagicMock()
        hass.config_entries.async_update_entry = MagicMock()

        sensor = NegotiatedPriceNumber(coordinator, entry)
        sensor.hass = hass
        sensor.async_write_ha_state = MagicMock()

        await sensor.async_set_native_value(75.0)

        assert coordinator.negotiated_price_gbp_per_mwh == 75.0
        hass.config_entries.async_update_entry.assert_called_once()
        call_args = hass.config_entries.async_update_entry.call_args
        assert call_args[0][0] == entry
        assert call_args[1]["options"][CONF_CFD_PRICE_GBP_PER_MWH] == 75.0

    @pytest.mark.asyncio
    async def test_owner_price_persists_to_options(self):
        """Changing owner price should update config entry options."""
        coordinator = MagicMock()
        coordinator.owner_price_pence_per_kwh = 5.0
        entry = MagicMock()
        entry.entry_id = "test"
        entry.options = {}

        hass = MagicMock()
        hass.config_entries.async_update_entry = MagicMock()

        sensor = OwnerPriceNumber(coordinator, entry)
        sensor.hass = hass
        sensor.async_write_ha_state = MagicMock()

        await sensor.async_set_native_value(8.5)

        assert coordinator.owner_price_pence_per_kwh == 8.5
        hass.config_entries.async_update_entry.assert_called_once()
        call_args = hass.config_entries.async_update_entry.call_args
        assert call_args[1]["options"][CONF_OWNER_PRICE_PENCE_PER_KWH] == 8.5

    def test_negotiated_price_reads_from_coordinator(self):
        """Native value should come from the coordinator attribute."""
        coordinator = MagicMock()
        coordinator.negotiated_price_gbp_per_mwh = 42.5
        entry = MagicMock()
        entry.entry_id = "test"

        sensor = NegotiatedPriceNumber(coordinator, entry)
        assert sensor.native_value == 42.5

    def test_owner_price_reads_from_coordinator(self):
        """Native value should come from the coordinator attribute."""
        coordinator = MagicMock()
        coordinator.owner_price_pence_per_kwh = 7.3
        entry = MagicMock()
        entry.entry_id = "test"

        sensor = OwnerPriceNumber(coordinator, entry)
        assert sensor.native_value == 7.3

    @pytest.mark.asyncio
    async def test_owner_rate_persists_to_options(self):
        """Changing the p/W rate should update config entry options.

        The rate has no restore_state path (it is new, so there is nothing
        pre-persistence to recover) -- options is its only source of truth,
        which makes this write the one that matters.
        """
        coordinator = MagicMock()
        coordinator.owner_rate_pence_per_w = 15.0
        entry = MagicMock()
        entry.entry_id = "test"
        entry.options = {}

        hass = MagicMock()
        hass.config_entries.async_update_entry = MagicMock()

        sensor = OwnerRateNumber(coordinator, entry)
        sensor.hass = hass
        sensor.async_write_ha_state = MagicMock()

        await sensor.async_set_native_value(21.0)

        assert coordinator.owner_rate_pence_per_w == 21.0
        hass.config_entries.async_update_entry.assert_called_once()
        call_args = hass.config_entries.async_update_entry.call_args
        assert call_args[0][0] == entry
        assert call_args[1]["options"][CONF_OWNER_RATE_PENCE_PER_W] == 21.0

    @pytest.mark.asyncio
    async def test_owner_rate_write_keeps_every_other_setting(self):
        """A rate write must not drop the settings it does not name.

        HA replaces entry.options wholesale, so a bare dict literal here would
        silently delete the prices and the scan interval (AGENTS.md rule 1).
        """
        coordinator = MagicMock()
        coordinator.owner_rate_pence_per_w = 0.0
        existing = {CONF_SITE_NAME: "Kirk Hill", CONF_SCAN_INTERVAL: 300}
        entry = MagicMock()
        entry.entry_id = "test"
        entry.options = dict(existing)

        hass = MagicMock()
        hass.config_entries.async_update_entry = MagicMock()

        sensor = OwnerRateNumber(coordinator, entry)
        sensor.hass = hass
        sensor.async_write_ha_state = MagicMock()

        await sensor.async_set_native_value(21.0)

        options = hass.config_entries.async_update_entry.call_args[1]["options"]
        assert options[CONF_OWNER_RATE_PENCE_PER_W] == 21.0
        assert options == {**existing, CONF_OWNER_RATE_PENCE_PER_W: 21.0}

    def test_owner_rate_reads_from_coordinator(self):
        """Native value should come from the coordinator attribute."""
        coordinator = MagicMock()
        coordinator.owner_rate_pence_per_w = 21.0
        entry = MagicMock()
        entry.entry_id = "test"

        sensor = OwnerRateNumber(coordinator, entry)
        assert sensor.native_value == 21.0


def _make_entry(options):
    """A config entry stand-in whose options actually mutate on write.

    The backfill reads entry.options at the start of its call and writes back at
    the end, and the two price entities share one entry. A MagicMock whose
    options never change would hide that interaction, so writes are applied for
    real here.
    """
    entry = MagicMock()
    entry.entry_id = "test"
    entry.options = dict(options)
    return entry


def _make_hass():
    hass = MagicMock()

    def _update(entry, options=None, **kwargs):
        entry.options = dict(options or {})

    hass.config_entries.async_update_entry = MagicMock(side_effect=_update)
    return hass


def _coordinator(cfd=50.0, owner=3.5):
    coordinator = MagicMock()
    coordinator.negotiated_price_gbp_per_mwh = cfd
    coordinator.owner_price_pence_per_kwh = owner
    return coordinator


async def _add(sensor, last_state):
    """Drive async_added_to_hass with a stubbed restore record."""
    if isinstance(last_state, str):
        last_state = MagicMock(state=last_state)
    with patch.object(sensor, "async_get_last_state", new_callable=AsyncMock, return_value=last_state):
        with patch.object(RestoreEntity, "async_added_to_hass", new_callable=AsyncMock):
            await sensor.async_added_to_hass()


class TestPriceBackfillUpgrade:
    """The <=v4.11.6 upgrade path: a price that only ever existed in restore_state.

    Before v4.13.0 these entities wrote nowhere. A user who set a price on
    v4.11.6 has it in exactly one place -- restore_state -- while the v5/v6
    migrations seeded 0.0 into options. If the backfill does not run, every
    earnings sensor reads 0.0 with no error anywhere. That is the data loss the
    ChatGPT review's "remove RestoreEntity" suggestion would have introduced, so
    these tests exist to make the recovery unremovable.
    """

    @pytest.mark.asyncio
    async def test_cfd_price_recovered_when_migration_flagged(self):
        coordinator = _coordinator(cfd=0.0)
        entry = _make_entry(
            {
                CONF_CFD_PRICE_GBP_PER_MWH: 0.0,
                CONF_PRICE_RESTORE_PENDING: [
                    CONF_CFD_PRICE_GBP_PER_MWH,
                    CONF_OWNER_PRICE_PENCE_PER_KWH,
                ],
            }
        )
        hass = _make_hass()

        sensor = NegotiatedPriceNumber(coordinator, entry)
        sensor.hass = hass
        await _add(sensor, "85.0")

        assert coordinator.negotiated_price_gbp_per_mwh == 85.0
        assert entry.options[CONF_CFD_PRICE_GBP_PER_MWH] == 85.0
        # Sibling price still outstanding -- must not be dropped by this entity.
        assert entry.options[CONF_PRICE_RESTORE_PENDING] == [CONF_OWNER_PRICE_PENCE_PER_KWH]

    @pytest.mark.asyncio
    async def test_owner_price_recovered_when_migration_flagged(self):
        coordinator = _coordinator(owner=0.0)
        entry = _make_entry(
            {
                CONF_OWNER_PRICE_PENCE_PER_KWH: 0.0,
                CONF_PRICE_RESTORE_PENDING: [
                    CONF_CFD_PRICE_GBP_PER_MWH,
                    CONF_OWNER_PRICE_PENCE_PER_KWH,
                ],
            }
        )
        hass = _make_hass()

        sensor = OwnerPriceNumber(coordinator, entry)
        sensor.hass = hass
        await _add(sensor, "4.2")

        assert coordinator.owner_price_pence_per_kwh == 4.2
        assert entry.options[CONF_OWNER_PRICE_PENCE_PER_KWH] == 4.2
        assert entry.options[CONF_PRICE_RESTORE_PENDING] == [CONF_CFD_PRICE_GBP_PER_MWH]

    @pytest.mark.asyncio
    async def test_marker_cleared_once_both_prices_recovered(self):
        """The marker is deleted, not left behind as a permanent false flag."""
        coordinator = _coordinator(cfd=0.0, owner=0.0)
        entry = _make_entry(
            {
                CONF_CFD_PRICE_GBP_PER_MWH: 0.0,
                CONF_OWNER_PRICE_PENCE_PER_KWH: 0.0,
                CONF_PRICE_RESTORE_PENDING: [
                    CONF_CFD_PRICE_GBP_PER_MWH,
                    CONF_OWNER_PRICE_PENCE_PER_KWH,
                ],
            }
        )
        hass = _make_hass()

        for entity_class, cfd_state, owner_state in (
            (NegotiatedPriceNumber, "85.0", None),
            (OwnerPriceNumber, None, "4.2"),
        ):
            sensor = entity_class(coordinator, entry)
            sensor.hass = hass
            await _add(sensor, cfd_state if entity_class is NegotiatedPriceNumber else owner_state)

        assert entry.options[CONF_CFD_PRICE_GBP_PER_MWH] == 85.0
        assert entry.options[CONF_OWNER_PRICE_PENCE_PER_KWH] == 4.2
        assert CONF_PRICE_RESTORE_PENDING not in entry.options

    @pytest.mark.asyncio
    async def test_backfill_preserves_unrelated_options(self):
        """HA replaces options wholesale, so a partial write would drop settings."""
        coordinator = _coordinator()
        entry = _make_entry(
            {
                CONF_SITE_NAME: "My Turbine",
                CONF_SCAN_INTERVAL: 120,
                CONF_PRICE_RESTORE_PENDING: [CONF_CFD_PRICE_GBP_PER_MWH],
            }
        )
        hass = _make_hass()

        sensor = NegotiatedPriceNumber(coordinator, entry)
        sensor.hass = hass
        await _add(sensor, "85.0")

        assert entry.options[CONF_SITE_NAME] == "My Turbine"
        assert entry.options[CONF_SCAN_INTERVAL] == 120
        assert entry.options[CONF_CFD_PRICE_GBP_PER_MWH] == 85.0

    @pytest.mark.asyncio
    async def test_flag_consumed_even_without_restore_record(self):
        """A missing or unparseable record must not wedge the marker forever.

        If the marker survived, the next restart would retry the read and could
        clobber a price the user has since set.
        """
        for bad_state in (None, "unavailable"):
            coordinator = _coordinator(cfd=50.0)
            entry = _make_entry(
                {
                    CONF_CFD_PRICE_GBP_PER_MWH: 50.0,
                    CONF_PRICE_RESTORE_PENDING: [CONF_CFD_PRICE_GBP_PER_MWH],
                }
            )
            hass = _make_hass()

            sensor = NegotiatedPriceNumber(coordinator, entry)
            sensor.hass = hass
            await _add(sensor, bad_state)

            assert coordinator.negotiated_price_gbp_per_mwh == 50.0, bad_state
            assert CONF_PRICE_RESTORE_PENDING not in entry.options, bad_state


class TestRestoreDoesNotOverrideOptions:
    """Steady state: options is authoritative and restore_state is never read.

    This is the defect the review identified. Before this guard, a stale
    restore record silently overwrote the saved price on every restart.
    """

    @pytest.mark.asyncio
    async def test_stale_restore_state_does_not_clobber_saved_price(self):
        coordinator = _coordinator(cfd=75.0)
        entry = _make_entry({CONF_CFD_PRICE_GBP_PER_MWH: 75.0})
        hass = _make_hass()

        sensor = NegotiatedPriceNumber(coordinator, entry)
        sensor.hass = hass

        get_state = AsyncMock(return_value=MagicMock(state="85.0"))
        with patch.object(sensor, "async_get_last_state", new_callable=AsyncMock) as mocked:
            mocked.side_effect = get_state
            with patch.object(RestoreEntity, "async_added_to_hass", new_callable=AsyncMock):
                await sensor.async_added_to_hass()
            # The read itself is the assertion: if it happens at all, a stale
            # record can overwrite the user's saved price.
            mocked.assert_not_called()

        assert coordinator.negotiated_price_gbp_per_mwh == 75.0
        assert entry.options[CONF_CFD_PRICE_GBP_PER_MWH] == 75.0

    @pytest.mark.asyncio
    async def test_marker_key_absent_means_no_write(self):
        """No marker -> not one write, not even a no-op rewrite of options."""
        coordinator = _coordinator(cfd=75.0)
        entry = _make_entry({CONF_CFD_PRICE_GBP_PER_MWH: 75.0})
        hass = _make_hass()

        sensor = NegotiatedPriceNumber(coordinator, entry)
        sensor.hass = hass
        await _add(sensor, "85.0")

        hass.config_entries.async_update_entry.assert_not_called()

    @pytest.mark.asyncio
    async def test_zero_price_is_respected_once_marker_consumed(self):
        """0.0 is a real, deliberate value ("no price") and must survive restarts.

        sensor.py reports projection_basis=no_owner_price_zero for it, so a user
        can meaningfully set it. A value-equality guard would wrongly treat
        this as un-backfilled forever.
        """
        coordinator = _coordinator(owner=0.0)
        entry = _make_entry(
            {
                CONF_OWNER_PRICE_PENCE_PER_KWH: 0.0,
                CONF_PRICE_RESTORE_PENDING: [CONF_OWNER_PRICE_PENCE_PER_KWH],
            }
        )
        hass = _make_hass()

        sensor = OwnerPriceNumber(coordinator, entry)
        sensor.hass = hass
        await _add(sensor, "9.9")

        # Marker present, so this is still a recovery: restore_state wins once.
        assert entry.options[CONF_OWNER_PRICE_PENCE_PER_KWH] == 9.9
        assert CONF_PRICE_RESTORE_PENDING not in entry.options

        # The user now deliberately sets 0.0, which the number entity persists
        # to options exactly as any other value would.
        sensor.async_write_ha_state = MagicMock()
        await sensor.async_set_native_value(0.0)
        assert entry.options[CONF_OWNER_PRICE_PENCE_PER_KWH] == 0.0

        # Restart: the coordinator is seeded from options by async_setup_entry
        # (get_owner_price), and the marker is gone, so restore_state is never
        # consulted and the deliberate 0.0 survives.
        coordinator.owner_price_pence_per_kwh = 0.0
        again = OwnerPriceNumber(coordinator, entry)
        again.hass = hass
        await _add(again, "9.9")

        assert coordinator.owner_price_pence_per_kwh == 0.0
        assert entry.options[CONF_OWNER_PRICE_PENCE_PER_KWH] == 0.0
