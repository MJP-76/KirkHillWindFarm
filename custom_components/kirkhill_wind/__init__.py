"""The Kirk Hill Wind Farm integration."""

from __future__ import annotations

import logging
from pathlib import Path

from homeassistant.components.frontend import (
    add_extra_js_url,
    remove_extra_js_url,
)
from homeassistant.components.http import StaticPathConfig
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.loader import LoaderError, async_get_integration

from .const import (
    CONF_BASE_URL,
    CONF_CFD_PRICE_GBP_PER_MWH,
    CONF_OWNER_PRICE_PENCE_PER_KWH,
    CONF_PRICE_RESTORE_PENDING,
    DEFAULT_BASE_URL,
    DEFAULT_CFD_PRICE_GBP_PER_MWH,
    DEFAULT_OWNER_PRICE_PENCE_PER_KWH,
    PLATFORMS,
)
from .coordinator import KirkHillWindCoordinator
from .dashboard import async_ensure_dashboard
from .device import get_farm_device_id
from .services import async_setup_services, async_unload_services
from .settings import (
    OPTION_KEYS,
    get_negotiated_price,
    get_owner_price,
    get_owner_rate,
    payment_tracking_enabled,
)

_LOGGER = logging.getLogger(__name__)
_FRONTEND_DIR = Path(__file__).parent / "frontend"
_FRONTEND_REGISTERED = "kirkhill_wind_frontend_registered"
_FRONTEND_URLS = "kirkhill_wind_frontend_urls"
_ETHEX_DOMAIN = "ethex"

_FRONTEND_CARDS: list[tuple[str, Path]] = [
    ("/kirkhill_wind/apexcharts-card.js", _FRONTEND_DIR / "apexcharts-card.js"),
    ("/kirkhill_wind/plotly-graph-card.js", _FRONTEND_DIR / "plotly-graph-card.js"),
    ("/kirkhill_wind/scada-card.js", _FRONTEND_DIR / "kirkhill-wind-scada-card.js"),
]

_FRONTEND_ASSETS: list[tuple[str, Path]] = [
    ("/kirkhill_wind/apexcharts.js", _FRONTEND_DIR / "apexcharts.js"),
]

# Keep in sync with the VERSION in config_flow.py.
_CONFIG_ENTRY_VERSION = 9


async def async_migrate_entry(hass: HomeAssistant, config_entry: ConfigEntry) -> bool:
    """Migrate a stored config entry to the current version."""
    if config_entry.version == _CONFIG_ENTRY_VERSION:
        return True

    entry_data = getattr(config_entry, "data", {}) or {}
    data = dict(entry_data)
    options = dict(getattr(config_entry, "options", {}) or {})

    if config_entry.version < 3:
        data.setdefault(CONF_BASE_URL, DEFAULT_BASE_URL)

    if config_entry.version < 4:
        data.pop("owner_share_percent", None)
        data.pop("owner_value_rate", None)

    # The two prices are settings, so they seed into options rather than data.
    # The defaults themselves are declared once in settings.SETTING_DEFAULTS.
    if config_entry.version < 5:
        options.setdefault(CONF_CFD_PRICE_GBP_PER_MWH, DEFAULT_CFD_PRICE_GBP_PER_MWH)

    if config_entry.version < 6:
        options.setdefault(
            CONF_OWNER_PRICE_PENCE_PER_KWH, DEFAULT_OWNER_PRICE_PENCE_PER_KWH
        )

    if config_entry.version < 7:
        data.pop("owner_projected_annual_earnings_gbp", None)
        data.pop("site_projected_annual_earnings_gbp", None)
        options.pop("owner_projected_annual_earnings_gbp", None)
        options.pop("site_projected_annual_earnings_gbp", None)

    if config_entry.version < 8:
        # Split connection details from settings. entry.data keeps only what
        # identifies the integration; everything the user can change moves to
        # entry.options.
        #
        # setdefault preserves existing precedence. Some of these keys may
        # already be in options, because the options flow and the number
        # entities have been writing there; where both mappings held a value,
        # options already won at runtime, so it must keep winning here.
        for key in OPTION_KEYS:
            if key in data:
                options.setdefault(key, data.pop(key))

    if config_entry.version < 9:
        # One-time price backfill. Before v4.13.0 the number entities wrote
        # nowhere, so a price the user set before then lives only in
        # restore_state, and the v5/v6 migrations above seeded the declared
        # default into options instead. Record which prices still need
        # recovering so number.py does it exactly once, then clears itself.
        # Without this, upgrading from <=v4.11.6 silently zeroes every
        # earnings sensor.
        #
        # Every pre-v9 entry is listed, not just those missing a price:
        # entry.options cannot distinguish "never set" from "set before
        # persistence existed", because the migration seeds the key. An entry
        # that already backfilled is a redundant read, not a wrong value --
        # restore_state and options agree by then.
        options[CONF_PRICE_RESTORE_PENDING] = [
            CONF_CFD_PRICE_GBP_PER_MWH,
            CONF_OWNER_PRICE_PENCE_PER_KWH,
        ]

    hass.config_entries.async_update_entry(
        config_entry, data=data, options=options, version=_CONFIG_ENTRY_VERSION
    )
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Kirk Hill Wind Farm from a config entry."""
    coordinator = KirkHillWindCoordinator(hass, entry)

    await coordinator.async_config_entry_first_refresh()

    entry.runtime_data = coordinator

    coordinator.farm_device_id = await get_farm_device_id(hass, entry)

    coordinator.negotiated_price_gbp_per_mwh = get_negotiated_price(entry)

    coordinator.owner_price_pence_per_kwh = get_owner_price(entry)

    coordinator.owner_rate_pence_per_w = get_owner_rate(entry)

    await async_setup_services(hass)

    entry.async_on_unload(entry.add_update_listener(_async_update_listener))

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    await _async_setup_payment_tracking(hass, entry)
    await _async_register_frontend(hass)
    await async_ensure_dashboard(hass, entry)

    return True


async def _async_update_listener(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Re-apply settings when the entry changes; reload on connection changes."""
    coordinator: KirkHillWindCoordinator | None = entry.runtime_data
    if coordinator is None:
        # async_unload_entry clears runtime_data, and an update landing in
        # that window must not dereference it.
        return

    if dict(entry.data) != coordinator.connection_data:
        # The API client captured entry.data at setup, so a new key or base URL
        # only takes effect on a reload. Home Assistant does not reload for us
        # after a reauth -- only async_update_reload_and_abort does, and that
        # helper reports usage when the entry has update listeners (an error
        # from 2026.12) -- so the listener schedules it, per HA's guidance.
        #
        # Reload rather than refresh: refreshing here would poll with the
        # stale key, 401, and start a second reauth flow immediately after the
        # one that just succeeded.
        hass.config_entries.async_schedule_reload(entry.entry_id)
        return

    coordinator.apply_options()
    await coordinator.async_request_refresh()
    await _async_setup_payment_tracking(hass, entry)
    await async_ensure_dashboard(hass, entry)


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)

    if unload_ok:
        entry.runtime_data = None
        await async_unload_services(hass)
        for url in hass.data.pop(_FRONTEND_URLS, ()):
            remove_extra_js_url(hass, url)

    return unload_ok


async def _async_register_frontend(hass: HomeAssistant) -> None:
    """Register bundled custom Lovelace cards."""
    if not hass.data.get(_FRONTEND_REGISTERED):
        await hass.http.async_register_static_paths(
            [
                StaticPathConfig(url, str(path), False)
                for url, path in _FRONTEND_CARDS + _FRONTEND_ASSETS
            ]
        )
        hass.data[_FRONTEND_REGISTERED] = True

    registered_urls = hass.data.setdefault(_FRONTEND_URLS, set())
    new_urls: set[str] = set()

    for url, path in _FRONTEND_CARDS:
        js_version = int(path.stat().st_mtime)
        new_url = f"{url}?v={js_version}"
        new_urls.add(new_url)
        if new_url not in registered_urls:
            add_extra_js_url(hass, new_url)

    for stale in registered_urls - new_urls:
        remove_extra_js_url(hass, stale)
    registered_urls.clear()
    registered_urls.update(new_urls)


async def _async_setup_payment_tracking(
    hass: HomeAssistant, entry: ConfigEntry
) -> None:
    """Initialize Ethex config flow when payment tracking is enabled."""
    if not payment_tracking_enabled(entry):
        return

    # Ask the loader whether Ethex is *installed* rather than reading
    # hass.config.components: a config-flow-only integration joins components
    # only once it already has an entry, so the "already configured" check
    # below always returned first and this branch made the flow start
    # unreachable -- while warning that Ethex was not installed, which is
    # usually false.
    try:
        ethex = await async_get_integration(hass, _ETHEX_DOMAIN)
    except LoaderError as err:
        # IntegrationNotFound covers "not installed"; a broken manifest lands
        # here too, and that must not take kirkhill's own setup down with it.
        _LOGGER.warning(
            "Payment tracking is enabled, but the Ethex integration is not "
            "available: %s",
            err,
        )
        return

    if not ethex.config_flow:
        _LOGGER.warning(
            "Payment tracking is enabled, but the Ethex integration has no config flow."
        )
        return

    if hass.config_entries.async_entries(_ETHEX_DOMAIN):
        return

    if hass.config_entries.flow.async_progress_by_handler(_ETHEX_DOMAIN):
        _LOGGER.info("Payment tracking enabled: Ethex config flow already in progress")
        return

    _LOGGER.info("Payment tracking enabled: starting Ethex configuration flow")
    await hass.config_entries.flow.async_init(
        _ETHEX_DOMAIN,
        context={"source": "user"},
    )
