"""The Kirk Hill Wind Farm integration."""
from __future__ import annotations

import logging
from pathlib import Path

from homeassistant.components import frontend
from homeassistant.components.frontend import (
    add_extra_js_url,
    remove_extra_js_url,
)
from homeassistant.components.http import StaticPathConfig
from homeassistant.components.lovelace import LOVELACE_DATA
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import (
    CONF_BASE_URL,
    CONF_CFD_PRICE_GBP_PER_MWH,
    CONF_CREATE_DASHBOARD,
    CONF_ENABLE_PAYMENT_TRACKING,
    CONF_OWNER_PRICE_PENCE_PER_KWH,
    DEFAULT_BASE_URL,
    DEFAULT_CFD_PRICE_GBP_PER_MWH,
    DEFAULT_CREATE_DASHBOARD,
    DEFAULT_ENABLE_PAYMENT_TRACKING,
    DEFAULT_OWNER_PRICE_PENCE_PER_KWH,
    PLATFORMS,
)
from .coordinator import KirkHillWindCoordinator
from .dashboard import (
    async_ensure_dashboard,
    async_reset_dashboard,
    dashboard_enabled,
)
from .device import get_farm_device_id
from .services import async_setup_services, async_unload_services

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
_CONFIG_ENTRY_VERSION = 7


async def async_migrate_entry(
    hass: HomeAssistant, config_entry: ConfigEntry
) -> bool:
    """Migrate a stored config entry to the current version."""
    if config_entry.version == _CONFIG_ENTRY_VERSION:
        return True

    entry_data = getattr(config_entry, 'data', {}) or {}
    data = dict(entry_data)

    if config_entry.version < 3:
        data.setdefault(CONF_BASE_URL, DEFAULT_BASE_URL)

    if config_entry.version < 4:
        data.pop("owner_share_percent", None)
        data.pop("owner_value_rate", None)

    if config_entry.version < 5:
        data.setdefault(CONF_CFD_PRICE_GBP_PER_MWH, DEFAULT_CFD_PRICE_GBP_PER_MWH)

    if config_entry.version < 6:
        data.setdefault(CONF_OWNER_PRICE_PENCE_PER_KWH, DEFAULT_OWNER_PRICE_PENCE_PER_KWH)

    options = dict(getattr(config_entry, "options", {}) or {})
    if config_entry.version < 7:
        data.pop("owner_projected_annual_earnings_gbp", None)
        data.pop("site_projected_annual_earnings_gbp", None)
        options.pop("owner_projected_annual_earnings_gbp", None)
        options.pop("site_projected_annual_earnings_gbp", None)

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

    coordinator.negotiated_price_gbp_per_mwh = float(
        entry.options.get(
            CONF_CFD_PRICE_GBP_PER_MWH,
            entry.data.get(CONF_CFD_PRICE_GBP_PER_MWH, DEFAULT_CFD_PRICE_GBP_PER_MWH),
        )
    )

    coordinator.owner_price_pence_per_kwh = float(
        entry.options.get(
            CONF_OWNER_PRICE_PENCE_PER_KWH,
            entry.data.get(
                CONF_OWNER_PRICE_PENCE_PER_KWH, DEFAULT_OWNER_PRICE_PENCE_PER_KWH
            ),
        )
    )

    await async_setup_services(hass)

    entry.async_on_unload(entry.add_update_listener(_async_update_listener))

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    await _async_setup_payment_tracking(hass, entry)
    await _async_register_frontend(hass)
    await async_ensure_dashboard(hass, entry)

    return True


async def _async_update_listener(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Re-apply scan interval when options change."""
    coordinator: KirkHillWindCoordinator = entry.runtime_data
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


async def _async_setup_payment_tracking(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Initialize Ethex config flow when payment tracking is enabled."""
    if not entry.options.get(
        CONF_ENABLE_PAYMENT_TRACKING,
        entry.data.get(CONF_ENABLE_PAYMENT_TRACKING, DEFAULT_ENABLE_PAYMENT_TRACKING),
    ):
        return

    if _ETHEX_DOMAIN not in hass.config.components:
        _LOGGER.warning(
            "Payment tracking is enabled, but the Ethex integration is not installed."
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
