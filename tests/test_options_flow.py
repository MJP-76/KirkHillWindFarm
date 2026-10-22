"""Tests for the config entry options flow."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from custom_components.kirkhill_wind.config_flow import KirkHillWindOptionsFlow
from custom_components.kirkhill_wind.const import (
    BOARD_FIGURES_MANUAL,
    BOARD_FIGURES_SOURCES,
    CONF_BOARD_FIGURES_SOURCE,
    CONF_CFD_PRICE_GBP_PER_MWH,
    CONF_CREATE_DASHBOARD,
    CONF_ENABLE_PAYMENT_TRACKING,
    CONF_OWNER_PRICE_PENCE_PER_KWH,
    CONF_SCAN_INTERVAL,
    CONF_SITE_NAME,
    DEFAULT_BASE_URL,
)
from custom_components.kirkhill_wind.settings import board_figures_source, form_defaults


def _make_entry(data: dict | None = None, options: dict | None = None) -> MagicMock:
    entry = MagicMock()
    entry.data = data if data is not None else {"api_key": "key", "base_url": DEFAULT_BASE_URL}
    entry.options = options if options is not None else {}
    return entry


async def _submit(entry: MagicMock, user_input: dict) -> dict:
    """Run the options flow and return the options dict it hands to Home Assistant."""
    flow = KirkHillWindOptionsFlow(entry)
    flow.async_create_entry = MagicMock(return_value={"type": "create_entry"})
    result = await flow.async_step_init(user_input)

    # The flow always terminates by creating an entry.
    assert result["type"] == "create_entry"
    flow.async_create_entry.assert_called_once()
    return flow.async_create_entry.call_args.kwargs["data"]


class TestOptionsFlowPreservesUnrelatedOptions:
    """The options form must not discard values it does not show.

    number.py persists the CFD and owner prices by writing them into
    entry.options. async_create_entry replaces the options mapping wholesale, so
    a flow that passes only its own form fields silently deletes those prices
    the next time anyone saves the options dialog.
    """

    @pytest.mark.asyncio
    async def test_preserves_cfd_and_owner_prices(self):
        entry = _make_entry(
            options={
                CONF_CFD_PRICE_GBP_PER_MWH: 85.0,
                CONF_OWNER_PRICE_PENCE_PER_KWH: 4.2,
            }
        )

        result = await _submit(
            entry,
            {
                CONF_SCAN_INTERVAL: 120,
                CONF_CREATE_DASHBOARD: True,
                CONF_ENABLE_PAYMENT_TRACKING: False,
            },
        )

        assert result[CONF_CFD_PRICE_GBP_PER_MWH] == 85.0, (
            "Saving the options dialog silently reset the negotiated CfD price. "
            "The form does not show this value, so it must be carried over."
        )
        assert result[CONF_OWNER_PRICE_PENCE_PER_KWH] == 4.2, (
            "Saving the options dialog silently reset the owner price."
        )

    @pytest.mark.asyncio
    async def test_preserves_site_name(self):
        """Site name is stored in options, so it must survive the form too."""
        entry = _make_entry(options={CONF_SITE_NAME: "Kirk Hill"})

        result = await _submit(
            entry,
            {
                CONF_SCAN_INTERVAL: 60,
                CONF_CREATE_DASHBOARD: True,
                CONF_ENABLE_PAYMENT_TRACKING: False,
            },
        )

        assert result[CONF_SITE_NAME] == "Kirk Hill"

    @pytest.mark.asyncio
    async def test_form_values_win_over_stale_options(self):
        """Explicit form input must override what was there before."""
        entry = _make_entry(options={CONF_SCAN_INTERVAL: 60})

        result = await _submit(
            entry,
            {
                CONF_SCAN_INTERVAL: 300,
                CONF_CREATE_DASHBOARD: False,
                CONF_ENABLE_PAYMENT_TRACKING: True,
            },
        )

        assert result[CONF_SCAN_INTERVAL] == 300
        assert result[CONF_CREATE_DASHBOARD] is False
        assert result[CONF_ENABLE_PAYMENT_TRACKING] is True

    @pytest.mark.asyncio
    async def test_does_not_mutate_the_entry_options_in_place(self):
        """Building the merged dict must not edit the live mapping."""
        original = {CONF_CFD_PRICE_GBP_PER_MWH: 85.0}
        entry = _make_entry(options=original)

        await _submit(
            entry,
            {
                CONF_SCAN_INTERVAL: 120,
                CONF_CREATE_DASHBOARD: True,
                CONF_ENABLE_PAYMENT_TRACKING: False,
            },
        )

        assert original == {CONF_CFD_PRICE_GBP_PER_MWH: 85.0}


class TestBoardFiguresSourceOption:
    """Where board payment figures come from: the shipped file or the card."""

    def test_defaults_to_repo(self):
        # On by default, and the file ships empty, so nothing changes until an
        # announcement is actually added to it.
        assert form_defaults(_make_entry())["board_figures_source"] == "repo"
        assert board_figures_source(_make_entry()) == "repo"
        assert set(BOARD_FIGURES_SOURCES) == {"repo", "manual"}

    @pytest.mark.asyncio
    async def test_form_offers_both_modes(self):
        flow = KirkHillWindOptionsFlow(_make_entry())
        flow.async_create_entry = MagicMock(return_value={"type": "create_entry"})
        result = await flow.async_step_init()

        assert result["type"] == "form"
        assert CONF_BOARD_FIGURES_SOURCE in result["data_schema"].schema

    @pytest.mark.asyncio
    async def test_manual_choice_survives_a_save(self):
        entry = _make_entry(
            options={
                CONF_SCAN_INTERVAL: 60,
                CONF_CREATE_DASHBOARD: True,
                CONF_ENABLE_PAYMENT_TRACKING: False,
                CONF_BOARD_FIGURES_SOURCE: BOARD_FIGURES_MANUAL,
            }
        )
        result = await _submit(
            entry,
            {
                CONF_SCAN_INTERVAL: 60,
                CONF_CREATE_DASHBOARD: True,
                CONF_ENABLE_PAYMENT_TRACKING: False,
                CONF_BOARD_FIGURES_SOURCE: BOARD_FIGURES_MANUAL,
            },
        )
        assert result[CONF_BOARD_FIGURES_SOURCE] == BOARD_FIGURES_MANUAL

        # Saving unrelated fields must not silently reset the choice: the flow
        # merges rather than replaces entry.options.
        entry2 = _make_entry(options=dict(result))
        result2 = await _submit(
            entry2,
            {
                CONF_SCAN_INTERVAL: 120,
                CONF_CREATE_DASHBOARD: True,
                CONF_ENABLE_PAYMENT_TRACKING: False,
            },
        )
        assert result2[CONF_BOARD_FIGURES_SOURCE] == BOARD_FIGURES_MANUAL
