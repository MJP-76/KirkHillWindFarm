"""Tests for __init__.py — config entry migration."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from homeassistant.loader import IntegrationNotFound

from custom_components.kirkhill_wind import (
    _CONFIG_ENTRY_VERSION,
    _async_setup_payment_tracking,
    _async_update_listener,
    async_migrate_entry,
)
from custom_components.kirkhill_wind.const import (
    CONF_API_KEY,
    CONF_BASE_URL,
    CONF_CFD_PRICE_GBP_PER_MWH,
    CONF_CREATE_DASHBOARD,
    CONF_ENABLE_PAYMENT_TRACKING,
    CONF_OWNER_PRICE_PENCE_PER_KWH,
    CONF_PRICE_RESTORE_PENDING,
    CONF_SCAN_INTERVAL,
    CONF_SITE_NAME,
    DEFAULT_BASE_URL,
    DEFAULT_CFD_PRICE_GBP_PER_MWH,
    DEFAULT_OWNER_PRICE_PENCE_PER_KWH,
    DEFAULT_SCAN_INTERVAL,
    DEFAULT_SITE_NAME,
)
from custom_components.kirkhill_wind.settings import (
    OPTION_KEYS,
    SETTING_DEFAULTS,
    get_negotiated_price,
    get_owner_price,
    get_scan_interval,
    get_setting,
    get_site_name,
    merge_options,
)


def _make_entry(version, data=None, options=None):
    """Return a fake config entry at a given schema version."""
    entry = MagicMock()
    entry.version = version
    entry.data = data or {}
    entry.options = options or {}
    return entry


class TestConfigMigration:
    """Verify config entry migration handles all version transitions."""

    @pytest.mark.asyncio
    async def test_already_current_version(self):
        """Migration should be a no-op when version is already current."""
        hass = MagicMock()
        entry = _make_entry(_CONFIG_ENTRY_VERSION, {CONF_API_KEY: "key"})

        result = await async_migrate_entry(hass, entry)
        assert result is True

    @pytest.mark.asyncio
    async def test_migration_from_v1(self):
        """v1 -> current should add base_url and all new fields."""
        hass = MagicMock()
        entry = _make_entry(1, {CONF_API_KEY: "key", "owner_share_percent": 50})

        result = await async_migrate_entry(hass, entry)
        assert result is True
        # Should have been updated to current version
        update_call = hass.config_entries.async_update_entry.call_args
        updated_data = update_call[1]["data"]
        assert update_call[1]["version"] == _CONFIG_ENTRY_VERSION
        # Credentials must survive the migration untouched.
        assert updated_data[CONF_API_KEY] == "key"
        # base_url is defaulted for pre-v3 entries.
        assert updated_data[CONF_BASE_URL] == DEFAULT_BASE_URL
        # Price fields added in v5 and v6 get their defaults. They are settings,
        # so since v8 they live in options rather than data.
        updated_options = update_call[1]["options"]
        assert updated_options[CONF_CFD_PRICE_GBP_PER_MWH] == DEFAULT_CFD_PRICE_GBP_PER_MWH
        assert updated_options[CONF_OWNER_PRICE_PENCE_PER_KWH] == DEFAULT_OWNER_PRICE_PENCE_PER_KWH
        assert CONF_CFD_PRICE_GBP_PER_MWH not in updated_data
        assert CONF_OWNER_PRICE_PENCE_PER_KWH not in updated_data
        # Dead keys removed in v4 are gone.
        assert "owner_share_percent" not in updated_data
        assert "owner_value_rate" not in updated_data
        # Projected earnings removed in v7 are gone.
        assert "owner_projected_annual_earnings_gbp" not in updated_data
        assert "site_projected_annual_earnings_gbp" not in updated_data

    @pytest.mark.asyncio
    async def test_migration_from_v3_removes_dead_keys(self):
        """v3 -> current should remove owner_share_percent and owner_value_rate."""
        hass = MagicMock()
        entry = _make_entry(
            3,
            {
                CONF_API_KEY: "key",
                CONF_BASE_URL: DEFAULT_BASE_URL,
                "owner_share_percent": 25,
                "owner_value_rate": 0.15,
            },
        )

        result = await async_migrate_entry(hass, entry)
        assert result is True
        update_call = hass.config_entries.async_update_entry.call_args
        updated_data = update_call[1]["data"]
        assert "owner_share_percent" not in updated_data
        assert "owner_value_rate" not in updated_data

    @pytest.mark.asyncio
    async def test_migration_from_v6_removes_projected_earnings(self):
        """v6 -> v7 should remove projected earnings from data and options."""
        hass = MagicMock()
        entry = _make_entry(
            6,
            {
                CONF_API_KEY: "key",
                CONF_BASE_URL: DEFAULT_BASE_URL,
                CONF_CFD_PRICE_GBP_PER_MWH: 50.0,
                CONF_OWNER_PRICE_PENCE_PER_KWH: 5.0,
                "owner_projected_annual_earnings_gbp": 1000,
                "site_projected_annual_earnings_gbp": 5000,
            },
            options={
                "owner_projected_annual_earnings_gbp": 1200,
                "site_projected_annual_earnings_gbp": 5500,
            },
        )

        result = await async_migrate_entry(hass, entry)
        assert result is True
        update_call = hass.config_entries.async_update_entry.call_args
        updated_data = update_call[1]["data"]
        updated_options = update_call[1]["options"]
        assert "owner_projected_annual_earnings_gbp" not in updated_data
        assert "site_projected_annual_earnings_gbp" not in updated_data
        assert "owner_projected_annual_earnings_gbp" not in updated_options
        assert "site_projected_annual_earnings_gbp" not in updated_options
        # The prices that were in data at v6 are carried into options, keeping
        # the 50.0/5.0 this entry had been running with.
        assert updated_options[CONF_CFD_PRICE_GBP_PER_MWH] == 50.0
        assert updated_options[CONF_OWNER_PRICE_PENCE_PER_KWH] == 5.0
        assert CONF_CFD_PRICE_GBP_PER_MWH not in updated_data
        assert CONF_OWNER_PRICE_PENCE_PER_KWH not in updated_data


class TestDataOptionsSeparation:
    """v8 moves every user-configurable setting out of entry.data.

    entry.data keeps connection details only; everything the user can change
    belongs in entry.options. Reading a setting was previously a two-level
    lookup that every call site had to repeat.
    """

    async def _migrated(self, entry):
        """Run the migration and return the (data, options) it wrote."""
        hass = MagicMock()
        result = await async_migrate_entry(hass, entry)
        assert result is True
        call = hass.config_entries.async_update_entry.call_args[1]
        return call["data"], call["options"]

    @pytest.mark.asyncio
    async def test_settings_move_from_data_to_options(self):
        entry = _make_entry(
            7,
            {
                CONF_API_KEY: "key",
                CONF_BASE_URL: DEFAULT_BASE_URL,
                CONF_SITE_NAME: "Kirk Hill",
                CONF_SCAN_INTERVAL: 300,
                CONF_CREATE_DASHBOARD: False,
                CONF_ENABLE_PAYMENT_TRACKING: True,
                CONF_CFD_PRICE_GBP_PER_MWH: 85.0,
                CONF_OWNER_PRICE_PENCE_PER_KWH: 4.2,
            },
        )

        data, options = await self._migrated(entry)

        # Every setting is now in options, with the value the entry was using.
        assert options[CONF_SITE_NAME] == "Kirk Hill"
        assert options[CONF_SCAN_INTERVAL] == 300
        assert options[CONF_CREATE_DASHBOARD] is False
        assert options[CONF_ENABLE_PAYMENT_TRACKING] is True
        assert options[CONF_CFD_PRICE_GBP_PER_MWH] == 85.0
        assert options[CONF_OWNER_PRICE_PENCE_PER_KWH] == 4.2

        # ...and none of them are left behind in data.
        for key in OPTION_KEYS:
            assert key not in data, f"{key} is a setting and must not stay in data"

    @pytest.mark.asyncio
    async def test_connection_details_stay_in_data(self):
        entry = _make_entry(
            7,
            {
                CONF_API_KEY: "key",
                CONF_BASE_URL: DEFAULT_BASE_URL,
                CONF_SITE_NAME: "Kirk Hill",
            },
        )

        data, options = await self._migrated(entry)

        assert data[CONF_API_KEY] == "key"
        assert data[CONF_BASE_URL] == DEFAULT_BASE_URL
        assert CONF_API_KEY not in options
        assert CONF_BASE_URL not in options

    @pytest.mark.asyncio
    async def test_existing_options_win_over_data(self):
        """Where both mappings held a key, options already won at runtime.

        The number entities and the options flow have both been writing to
        options, so a value present in both must not be rolled back to the
        stale copy in data.
        """
        entry = _make_entry(
            7,
            {
                CONF_API_KEY: "key",
                CONF_BASE_URL: DEFAULT_BASE_URL,
                CONF_SCAN_INTERVAL: 60,
                CONF_CFD_PRICE_GBP_PER_MWH: 0.0,
            },
            options={
                CONF_SCAN_INTERVAL: 900,
                CONF_CFD_PRICE_GBP_PER_MWH: 85.0,
            },
        )

        data, options = await self._migrated(entry)

        assert options[CONF_SCAN_INTERVAL] == 900
        assert options[CONF_CFD_PRICE_GBP_PER_MWH] == 85.0
        assert CONF_SCAN_INTERVAL not in data
        assert CONF_CFD_PRICE_GBP_PER_MWH not in data

    @pytest.mark.asyncio
    async def test_unknown_keys_are_left_alone(self):
        """Only declared settings move; anything else in data is preserved."""
        entry = _make_entry(
            7,
            {
                CONF_API_KEY: "key",
                CONF_BASE_URL: DEFAULT_BASE_URL,
                "some_future_key": "keep me",
            },
        )

        data, options = await self._migrated(entry)

        assert data["some_future_key"] == "keep me"
        assert "some_future_key" not in options

    @pytest.mark.asyncio
    async def test_entry_without_settings_in_data(self):
        """An entry that already keeps only connection data migrates cleanly."""
        entry = _make_entry(
            7,
            {
                CONF_API_KEY: "key",
                CONF_BASE_URL: DEFAULT_BASE_URL,
            },
        )

        data, options = await self._migrated(entry)

        assert data == {CONF_API_KEY: "key", CONF_BASE_URL: DEFAULT_BASE_URL}
        # No settings are invented, but the v9 price-backfill marker is added --
        # it is not a setting, so compare on the setting keys only.
        assert not set(options) & set(OPTION_KEYS)
        assert CONF_PRICE_RESTORE_PENDING in options


class TestPriceBackfillMigration:
    """v9 marks pre-v4.13.0 entries so their prices can be recovered.

    The scenario this exists for: a user on v4.11.6 set a price. At that version
    the number entities wrote nowhere, so the value lived only in restore_state.
    The v5/v6 migrations could not see it and seeded the declared default (0.0).
    Upgrading would therefore zero every earnings sensor, silently -- no error,
    just £0 on the dashboard.
    """

    async def _migrated(self, entry):
        hass = MagicMock()
        result = await async_migrate_entry(hass, entry)
        assert result is True
        call = hass.config_entries.async_update_entry.call_args[1]
        return call["data"], call["options"], call["version"]

    @pytest.mark.asyncio
    async def test_v4_11_6_entry_is_flagged_for_backfill(self):
        """A v4 entry (the schema version v4.11.6 wrote) gets the marker."""
        data, options, version = await self._migrated(
            _make_entry(4, {CONF_API_KEY: "key", CONF_BASE_URL: DEFAULT_BASE_URL})
        )

        assert version == _CONFIG_ENTRY_VERSION
        # The migrations seed the declared default -- they cannot recover the
        # real price, which is the whole reason the marker exists.
        assert options[CONF_CFD_PRICE_GBP_PER_MWH] == DEFAULT_CFD_PRICE_GBP_PER_MWH
        assert options[CONF_OWNER_PRICE_PENCE_PER_KWH] == DEFAULT_OWNER_PRICE_PENCE_PER_KWH
        assert set(options[CONF_PRICE_RESTORE_PENDING]) == {
            CONF_CFD_PRICE_GBP_PER_MWH,
            CONF_OWNER_PRICE_PENCE_PER_KWH,
        }

    @pytest.mark.asyncio
    async def test_marker_covers_both_prices_separately(self):
        """A list, not a single boolean.

        The two number entities share one entry. With a shared boolean, whichever
        set up first would clear it and the other price would never be
        recovered -- a silent, partial data loss.
        """
        _, options, _ = await self._migrated(_make_entry(4, {CONF_API_KEY: "key", CONF_BASE_URL: DEFAULT_BASE_URL}))

        pending = options[CONF_PRICE_RESTORE_PENDING]
        assert isinstance(pending, list)
        assert len(pending) == 2
        assert len(set(pending)) == 2, "a price must not appear twice"

    @pytest.mark.asyncio
    async def test_v8_entry_also_flagged(self):
        """Entries written by v4.13.x never backfilled, because nothing asked them to.

        They are consistent already, so this is a redundant restore read at
        worst -- the alternative is a value-equality guess that would treat a
        deliberate 0.0 as un-backfilled forever.
        """
        _, options, _ = await self._migrated(
            _make_entry(
                8,
                {CONF_API_KEY: "key", CONF_BASE_URL: DEFAULT_BASE_URL},
                {CONF_CFD_PRICE_GBP_PER_MWH: 85.0, CONF_OWNER_PRICE_PENCE_PER_KWH: 4.2},
            )
        )

        assert CONF_PRICE_RESTORE_PENDING in options
        # Existing values must not be disturbed by the migration itself.
        assert options[CONF_CFD_PRICE_GBP_PER_MWH] == 85.0
        assert options[CONF_OWNER_PRICE_PENCE_PER_KWH] == 4.2

    @pytest.mark.asyncio
    async def test_already_migrated_entry_is_not_reflagged(self):
        """Once at v9 the entry returns early, so the marker is not re-added.

        Re-adding it would make every subsequent restart retry the backfill, and
        a stale restore record could then overwrite a price the user has since
        changed.
        """
        hass = MagicMock()
        entry = _make_entry(
            _CONFIG_ENTRY_VERSION,
            {CONF_API_KEY: "key", CONF_BASE_URL: DEFAULT_BASE_URL},
            {CONF_CFD_PRICE_GBP_PER_MWH: 85.0},
        )

        assert await async_migrate_entry(hass, entry) is True
        hass.config_entries.async_update_entry.assert_not_called()

    @pytest.mark.asyncio
    async def test_marker_is_not_a_setting(self):
        """It must not appear in the options form or in get_setting's keyspace."""
        assert CONF_PRICE_RESTORE_PENDING not in OPTION_KEYS
        assert CONF_PRICE_RESTORE_PENDING not in SETTING_DEFAULTS
        with pytest.raises(KeyError):
            get_setting(_make_entry(9), CONF_PRICE_RESTORE_PENDING)


class TestSettingsAccess:
    """Reads go through settings.py, which owns defaults and option keys."""

    def _entry(self, data=None, options=None):
        return _make_entry(8, data or {}, options)

    def test_prefers_options(self):
        assert get_site_name(_make_entry(8, options={CONF_SITE_NAME: "Custom"})) == "Custom"

    def test_falls_back_to_declared_default(self):
        entry = _make_entry(8)
        assert get_site_name(entry) == DEFAULT_SITE_NAME
        assert get_scan_interval(entry) == DEFAULT_SCAN_INTERVAL
        assert get_negotiated_price(entry) == DEFAULT_CFD_PRICE_GBP_PER_MWH
        assert get_owner_price(entry) == DEFAULT_OWNER_PRICE_PENCE_PER_KWH

    def test_settings_in_data_are_ignored(self):
        """data is connection-only, so a stale copy there must not win.

        This guards against the split silently regressing: if a reader went
        back to consulting data, this test would fail.
        """
        entry = _make_entry(8, {CONF_SITE_NAME: "Stale Name", CONF_SCAN_INTERVAL: 5})
        assert get_site_name(entry) == DEFAULT_SITE_NAME
        assert get_scan_interval(entry) == DEFAULT_SCAN_INTERVAL

    def test_option_keys_cover_every_declared_default(self):
        assert set(OPTION_KEYS) == set(SETTING_DEFAULTS)

    def test_unknown_key_is_rejected(self):
        with pytest.raises(KeyError):
            get_setting(_make_entry(8), "not_a_setting")

    def test_merge_options_lets_the_form_win(self):
        merged = merge_options(
            {CONF_CFD_PRICE_GBP_PER_MWH: 85.0, CONF_SITE_NAME: "Kirk Hill"},
            {CONF_SCAN_INTERVAL: 120},
        )
        assert merged[CONF_CFD_PRICE_GBP_PER_MWH] == 85.0
        assert merged[CONF_SITE_NAME] == "Kirk Hill"
        assert merged[CONF_SCAN_INTERVAL] == 120

    def test_merge_options_does_not_mutate_either_input(self):
        existing = {CONF_CFD_PRICE_GBP_PER_MWH: 85.0}
        incoming = {CONF_SCAN_INTERVAL: 120}
        merge_options(existing, incoming)
        assert existing == {CONF_CFD_PRICE_GBP_PER_MWH: 85.0}
        assert incoming == {CONF_SCAN_INTERVAL: 120}


class TestManifestVersion:
    """Verify manifest version matches VERSION file."""

    def test_manifest_version_matches_version_file(self):
        import json
        from pathlib import Path

        root = Path(__file__).parent.parent
        manifest = json.loads((root / "custom_components/kirkhill_wind/manifest.json").read_text())
        version_file = (root / "VERSION").read_text().strip()

        assert manifest["version"] == version_file, (
            f"manifest.json version ({manifest['version']}) != VERSION file ({version_file})"
        )


class TestUpdateListenerReloadDecision:
    """entry.data changes reload; entry.options changes are applied in place.

    The API client captures api_key/base_url when the coordinator is built, so
    a reauth -- which writes entry.data -- only reaches the client through a
    reload. Home Assistant does not reload for us after a reauth (only
    async_update_reload_and_abort does, and that helper reports usage when the
    entry has update listeners), so the listener is what has to decide.
    """

    def _make_entry(self, *, connection_changed: bool):
        entry = MagicMock()
        entry.entry_id = "entry-1"
        entry.data = {CONF_API_KEY: "new-key", CONF_BASE_URL: DEFAULT_BASE_URL}
        entry.options = {}
        coordinator = MagicMock()
        coordinator.connection_data = (
            {CONF_API_KEY: "old-key", CONF_BASE_URL: DEFAULT_BASE_URL} if connection_changed else dict(entry.data)
        )
        coordinator.async_request_refresh = AsyncMock()
        entry.runtime_data = coordinator
        return entry, coordinator

    @pytest.mark.asyncio
    async def test_connection_change_schedules_reload_without_refreshing(self, hass):
        """Refreshing here would poll with the stale key and restart reauth."""
        entry, coordinator = self._make_entry(connection_changed=True)

        await _async_update_listener(hass, entry)

        hass.config_entries.async_schedule_reload.assert_called_once_with(entry.entry_id)
        coordinator.async_request_refresh.assert_not_called()
        coordinator.apply_options.assert_not_called()

    @pytest.mark.asyncio
    async def test_options_change_applies_and_refreshes_without_reload(self, hass):
        """Prices and the scan interval must keep applying without a reload."""
        entry, coordinator = self._make_entry(connection_changed=False)

        await _async_update_listener(hass, entry)

        hass.config_entries.async_schedule_reload.assert_not_called()
        coordinator.apply_options.assert_called_once()
        coordinator.async_request_refresh.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_unloaded_entry_is_ignored(self, hass):
        """runtime_data is None once async_unload_entry has run."""
        entry, _ = self._make_entry(connection_changed=False)
        entry.runtime_data = None

        await _async_update_listener(hass, entry)  # must not raise

        hass.config_entries.async_schedule_reload.assert_not_called()


class TestPaymentTrackingSetup:
    """Payment tracking starts Ethex's config flow only when it can.

    The old check asked ``hass.config.components`` whether Ethex was
    installed, but a config-flow-only integration joins components only once
    it already has an entry -- so the "already configured" test below always
    returned first, the flow-start branch was unreachable, and users were told
    Ethex was not installed when it was.
    """

    @staticmethod
    def _entry(*, enabled: bool = True) -> MagicMock:
        entry = MagicMock()
        entry.entry_id = "test_entry"
        entry.options = {CONF_ENABLE_PAYMENT_TRACKING: enabled}
        return entry

    @staticmethod
    def _flow(hass, *, entries=(), progress=()):
        hass.config_entries.async_entries = MagicMock(return_value=list(entries))
        hass.config_entries.flow.async_progress_by_handler = MagicMock(return_value=list(progress))
        hass.config_entries.flow.async_init = AsyncMock()
        return hass.config_entries.flow

    @pytest.mark.asyncio
    async def test_installed_but_unconfigured_starts_the_flow(self, hass):
        flow = self._flow(hass)

        with patch(
            "custom_components.kirkhill_wind.async_get_integration",
            AsyncMock(return_value=MagicMock(config_flow=True)),
        ):
            await _async_setup_payment_tracking(hass, self._entry())

        flow.async_init.assert_awaited_once_with("ethex", context={"source": "user"})

    @pytest.mark.asyncio
    async def test_not_installed_starts_nothing(self, hass):
        flow = self._flow(hass)

        with patch(
            "custom_components.kirkhill_wind.async_get_integration",
            AsyncMock(side_effect=IntegrationNotFound("ethex")),
        ):
            await _async_setup_payment_tracking(hass, self._entry())

        flow.async_init.assert_not_called()

    @pytest.mark.asyncio
    async def test_already_configured_starts_nothing(self, hass):
        flow = self._flow(hass, entries=[MagicMock()])

        with patch(
            "custom_components.kirkhill_wind.async_get_integration",
            AsyncMock(return_value=MagicMock(config_flow=True)),
        ):
            await _async_setup_payment_tracking(hass, self._entry())

        flow.async_init.assert_not_called()

    @pytest.mark.asyncio
    async def test_disabled_payment_tracking_starts_nothing(self, hass):
        flow = self._flow(hass)

        with patch("custom_components.kirkhill_wind.async_get_integration", AsyncMock()) as loader:
            await _async_setup_payment_tracking(hass, self._entry(enabled=False))

        loader.assert_not_awaited()
        flow.async_init.assert_not_called()
