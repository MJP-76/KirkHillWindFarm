DOMAIN = "kirkhill_wind"

DEFAULT_NAME = "Kirk Hill Wind Farm"

# Configuration keys
CONF_API_KEY = "api_key"
CONF_BASE_URL = "base_url"
CONF_CREATE_DASHBOARD = "create_dashboard"
CONF_ENABLE_PAYMENT_TRACKING = "enable_payment_tracking"
CONF_SITE_NAME = "site_name"
CONF_SCAN_INTERVAL = "scan_interval"
CONF_CFD_PRICE_GBP_PER_MWH = "cfd_price_gbp_per_mwh"
CONF_OWNER_PRICE_PENCE_PER_KWH = "owner_price_pence_per_kwh"

DEFAULT_BASE_URL = "https://dashboard.kirkhillcoop.org"
DEFAULT_CREATE_DASHBOARD = True
DEFAULT_ENABLE_PAYMENT_TRACKING = False
DEFAULT_SITE_NAME = "Kirk Hill Wind Farm"
DEFAULT_SCAN_INTERVAL = 60  # seconds between API polls
DEFAULT_CFD_PRICE_GBP_PER_MWH = 0.0
DEFAULT_OWNER_PRICE_PENCE_PER_KWH = 0.0

MIN_SCAN_INTERVAL = 30
MAX_SCAN_INTERVAL = 3600

# Generation scopes from the OpenAPI spec.
SCOPE_OWNER = "owner"
SCOPE_SITE = "site"
SCOPES = [SCOPE_OWNER, SCOPE_SITE]

# Dashboard timeframe labels mapped to API range values.
TIMEFRAME_TO_RANGE = {
    "yesterday": "yesterday",
    "today": "today",
    "week": "7d",
    "month": "30d",
    "ytd": "ytd",
    "alltime": "all",
}
# Fixed (non-year) timeframes. Past calendar years are added dynamically via
# yearly_timeframes() so future years are picked up without code changes.
TIMEFRAME_ORDER = ("yesterday", "today", "week", "month", "ytd", "year", "alltime")

# First calendar year with farm generation data — the all-time window starts
# 2024-04-25 (the API-reported commissioning date). Past-year timeframes run
# from this year to the last complete year; the current year is the `year`
# timeframe (range=<current year>).
PAST_YEAR_START = 2024


def yearly_timeframes(current_year: int | None = None) -> tuple[str, ...]:
    """Return past-year timeframe keys, e.g. ('year_2024', 'year_2025').

    Derived from the commissioning year to the last complete year so any future
    years are added automatically: their kWh join the All time sum and their
    sensors appear after the next Home Assistant restart.
    """
    if current_year is None:
        from homeassistant.util import dt as dt_util

        current_year = dt_util.now().year
    return tuple(f"year_{year}" for year in range(PAST_YEAR_START, current_year))

PLATFORMS = ["sensor", "binary_sensor", "number"]
