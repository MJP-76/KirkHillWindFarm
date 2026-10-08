"""Single source of truth for user-configurable settings.

Config entry ``data`` holds only connection details -- the API key and base
URL -- which identify the integration and are set once by the config flow.
Everything the user can change lives in ``options`` and is edited through the
options flow.

Before this split both mappings carried the same keys and every reader did its
own two-level lookup::

    entry.options.get(KEY, entry.data.get(KEY, DEFAULT))

That put the precedence rule in eight places, meant two sources of truth for one
value, and let the options form silently discard settings it does not display.
Reading a setting is now a single lookup here, and ``OPTION_KEYS`` is what the
migration uses to decide what moves between the two mappings.
"""

from __future__ import annotations

from typing import Any

from homeassistant.config_entries import ConfigEntry

from .const import (
    CONF_CFD_PRICE_GBP_PER_MWH,
    CONF_CREATE_DASHBOARD,
    CONF_ENABLE_PAYMENT_TRACKING,
    CONF_OWNER_PRICE_PENCE_PER_KWH,
    CONF_OWNER_RATE_PENCE_PER_W,
    CONF_SCAN_INTERVAL,
    CONF_SITE_NAME,
    DEFAULT_CFD_PRICE_GBP_PER_MWH,
    DEFAULT_CREATE_DASHBOARD,
    DEFAULT_ENABLE_PAYMENT_TRACKING,
    DEFAULT_OWNER_PRICE_PENCE_PER_KWH,
    DEFAULT_OWNER_RATE_PENCE_PER_W,
    DEFAULT_SCAN_INTERVAL,
    DEFAULT_SITE_NAME,
)

# Default for every key stored in entry.options.
SETTING_DEFAULTS: dict[str, Any] = {
    CONF_SITE_NAME: DEFAULT_SITE_NAME,
    CONF_SCAN_INTERVAL: DEFAULT_SCAN_INTERVAL,
    CONF_CREATE_DASHBOARD: DEFAULT_CREATE_DASHBOARD,
    CONF_ENABLE_PAYMENT_TRACKING: DEFAULT_ENABLE_PAYMENT_TRACKING,
    CONF_CFD_PRICE_GBP_PER_MWH: DEFAULT_CFD_PRICE_GBP_PER_MWH,
    CONF_OWNER_PRICE_PENCE_PER_KWH: DEFAULT_OWNER_PRICE_PENCE_PER_KWH,
    CONF_OWNER_RATE_PENCE_PER_W: DEFAULT_OWNER_RATE_PENCE_PER_W,
}

# Keys that belong in entry.options and must never appear in entry.data.
OPTION_KEYS: tuple[str, ...] = tuple(SETTING_DEFAULTS)

# Fields the options form shows. Settings outside this set (the two prices, and
# the site name) are stored in options but edited elsewhere, so the form must
# merge rather than replace -- see the options flow.
OPTIONS_FORM_KEYS: tuple[str, ...] = (
    CONF_SCAN_INTERVAL,
    CONF_CREATE_DASHBOARD,
    CONF_ENABLE_PAYMENT_TRACKING,
)


def get_setting(entry: ConfigEntry, key: str) -> Any:
    """Return a setting from options, falling back to its declared default."""
    try:
        default = SETTING_DEFAULTS[key]
    except KeyError:
        raise KeyError(f"{key} is not a Kirk Hill Wind Farm setting") from None
    return entry.options.get(key, default)


def get_scan_interval(entry: ConfigEntry) -> int:
    """Return the API poll interval in seconds."""
    return int(get_setting(entry, CONF_SCAN_INTERVAL))


def get_site_name(entry: ConfigEntry) -> str:
    """Return the display name for this site."""
    return str(get_setting(entry, CONF_SITE_NAME))


def dashboard_enabled(entry: ConfigEntry) -> bool:
    """Return whether the Lovelace dashboard tab should be created."""
    return bool(get_setting(entry, CONF_CREATE_DASHBOARD))


def payment_tracking_enabled(entry: ConfigEntry) -> bool:
    """Return whether Ethex payment tracking should be set up."""
    return bool(get_setting(entry, CONF_ENABLE_PAYMENT_TRACKING))


def get_negotiated_price(entry: ConfigEntry) -> float:
    """Return the negotiated CfD price in GBP per MWh."""
    return float(get_setting(entry, CONF_CFD_PRICE_GBP_PER_MWH))


def get_owner_price(entry: ConfigEntry) -> float:
    """Return the owner price in pence per kWh."""
    return float(get_setting(entry, CONF_OWNER_PRICE_PENCE_PER_KWH))


def get_owner_rate(entry: ConfigEntry) -> float:
    """Return the member savings rate in pence per owned watt."""
    return float(get_setting(entry, CONF_OWNER_RATE_PENCE_PER_W))


def form_defaults(entry: ConfigEntry) -> dict[str, Any]:
    """Return the current value of every field the options form shows."""
    return {key: get_setting(entry, key) for key in OPTIONS_FORM_KEYS}


def merge_options(existing: dict[str, Any], incoming: dict[str, Any]) -> dict[str, Any]:
    """Combine stored options with a subset of keys, letting the subset win.

    Home Assistant replaces entry.options wholesale whenever options are
    written, so anything not carried across here is lost. Every writer of
    options must go through this -- the options flow, which submits only the
    fields its form shows, and the number entities, which write one price at a
    time.
    """
    return {**existing, **incoming}
