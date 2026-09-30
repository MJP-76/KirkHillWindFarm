"""Tests for number entities — persistence to config entry options."""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from homeassistant.helpers.restore_state import RestoreEntity

from custom_components.kirkhill_wind.const import (
    CONF_CFD_PRICE_GBP_PER_MWH,
    CONF_OWNER_PRICE_PENCE_PER_KWH,
)
from custom_components.kirkhill_wind.number import (
    NegotiatedPriceNumber,
    OwnerPriceNumber,
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


class TestRestorePersistsToOptions:
    """RestoreEntity must write restored values back to entry.options.

    Without this, the coordinator would use the restored value while
    entry.options keeps the stale default — so the options form and
    diagnostics would show the wrong number.
    """

    @staticmethod
    def _make_sensor(entity_class, coordinator, entry, hass):
        sensor = entity_class(coordinator, entry)
        sensor.hass = hass
        return sensor

    @pytest.mark.asyncio
    async def test_cfd_restore_writes_to_options(self):
        coordinator = MagicMock()
        coordinator.negotiated_price_gbp_per_mwh = 50.0
        entry = MagicMock()
        entry.entry_id = "test"
        entry.options = {}
        hass = MagicMock()
        hass.config_entries.async_update_entry = MagicMock()

        sensor = self._make_sensor(NegotiatedPriceNumber, coordinator, entry, hass)

        last_state = MagicMock()
        last_state.state = "85.0"

        with patch.object(sensor, "async_get_last_state", new_callable=AsyncMock, return_value=last_state):
            with patch.object(RestoreEntity, "async_added_to_hass", new_callable=AsyncMock):
                await sensor.async_added_to_hass()

        assert coordinator.negotiated_price_gbp_per_mwh == 85.0
        hass.config_entries.async_update_entry.assert_called_once()
        call_args = hass.config_entries.async_update_entry.call_args
        assert call_args[0][0] == entry
        assert call_args[1]["options"][CONF_CFD_PRICE_GBP_PER_MWH] == 85.0

    @pytest.mark.asyncio
    async def test_owner_restore_writes_to_options(self):
        coordinator = MagicMock()
        coordinator.owner_price_pence_per_kwh = 3.5
        entry = MagicMock()
        entry.entry_id = "test"
        entry.options = {}
        hass = MagicMock()
        hass.config_entries.async_update_entry = MagicMock()

        sensor = self._make_sensor(OwnerPriceNumber, coordinator, entry, hass)

        last_state = MagicMock()
        last_state.state = "4.2"

        with patch.object(sensor, "async_get_last_state", new_callable=AsyncMock, return_value=last_state):
            with patch.object(RestoreEntity, "async_added_to_hass", new_callable=AsyncMock):
                await sensor.async_added_to_hass()

        assert coordinator.owner_price_pence_per_kwh == 4.2
        hass.config_entries.async_update_entry.assert_called_once()
        call_args = hass.config_entries.async_update_entry.call_args
        assert call_args[1]["options"][CONF_OWNER_PRICE_PENCE_PER_KWH] == 4.2

    @pytest.mark.asyncio
    async def test_no_restore_when_no_last_state(self):
        """If there's no saved state, async_added_to_hass should not write to options."""
        coordinator = MagicMock()
        coordinator.negotiated_price_gbp_per_mwh = 50.0
        entry = MagicMock()
        entry.entry_id = "test"
        entry.options = {}
        hass = MagicMock()
        hass.config_entries.async_update_entry = MagicMock()

        sensor = self._make_sensor(NegotiatedPriceNumber, coordinator, entry, hass)

        with patch.object(sensor, "async_get_last_state", new_callable=AsyncMock, return_value=None):
            with patch.object(RestoreEntity, "async_added_to_hass", new_callable=AsyncMock):
                await sensor.async_added_to_hass()

        hass.config_entries.async_update_entry.assert_not_called()

    @pytest.mark.asyncio
    async def test_no_restore_when_state_is_unparsable(self):
        """An unparseable state should be silently ignored."""
        coordinator = MagicMock()
        coordinator.negotiated_price_gbp_per_mwh = 50.0
        entry = MagicMock()
        entry.entry_id = "test"
        entry.options = {}
        hass = MagicMock()
        hass.config_entries.async_update_entry = MagicMock()

        sensor = self._make_sensor(NegotiatedPriceNumber, coordinator, entry, hass)

        last_state = MagicMock()
        last_state.state = "unavailable"

        with patch.object(sensor, "async_get_last_state", new_callable=AsyncMock, return_value=last_state):
            with patch.object(RestoreEntity, "async_added_to_hass", new_callable=AsyncMock):
                await sensor.async_added_to_hass()

        hass.config_entries.async_update_entry.assert_not_called()
        assert coordinator.negotiated_price_gbp_per_mwh == 50.0
