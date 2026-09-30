"""Tests for number entities — persistence to config entry options."""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

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