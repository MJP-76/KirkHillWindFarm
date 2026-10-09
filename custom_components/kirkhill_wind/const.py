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
CONF_OWNER_RATE_PENCE_PER_W = "owner_rate_pence_per_w"

# One-shot marker, not a user setting. See AGENTS.md rule 3.
#
# Until v4.13.0 the number entities persisted nowhere, so a price a user set
# before then exists only in restore_state. The v5/v6 migrations could not
# recover it -- they seeded the declared default -- which means entry.options
# alone cannot tell "the user never set a price" apart from "the user set it
# before persistence existed". The v9 migration stores the affected option keys
# here so the restore read happens exactly once, and only for the entries that
# need it.
#
# Value is a list of the option keys still awaiting backfill, because the two
# number entities set up separately and each must consume only its own key --
# a single shared boolean would let whichever entity ran first clear the flag
# and silently skip the other.
#
# Deliberately not in settings.SETTING_DEFAULTS: it is not a setting, must not
# appear in the options form, and get_setting() should reject it.
CONF_PRICE_RESTORE_PENDING = "price_restore_pending"

DEFAULT_BASE_URL = "https://dashboard.kirkhillcoop.org"
DEFAULT_CREATE_DASHBOARD = True
DEFAULT_ENABLE_PAYMENT_TRACKING = False
DEFAULT_SITE_NAME = "Kirk Hill Wind Farm"
DEFAULT_SCAN_INTERVAL = 60  # seconds between API polls
DEFAULT_CFD_PRICE_GBP_PER_MWH = 0.0
DEFAULT_OWNER_PRICE_PENCE_PER_KWH = 0.0
# Declared member-savings rate in pence per owned watt. Members are paid for
# watts owned, not kWh generated, and the period never enters the calculation:
# the board reviews its finances and declares a payment (a yearly figure it
# quotes is an equivalence for that declaration, not an accrual rate).
# 0.0 means "nothing declared yet".
DEFAULT_OWNER_RATE_PENCE_PER_W = 0.0

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
