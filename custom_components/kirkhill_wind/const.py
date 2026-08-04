DOMAIN = "kirkhill_wind"

DEFAULT_NAME = "Kirk Hill Wind Farm"

# Configuration keys
CONF_API_KEY = "api_key"
CONF_BASE_URL = "base_url"
CONF_CREATE_DASHBOARD = "create_dashboard"
CONF_ENABLE_PAYMENT_TRACKING = "enable_payment_tracking"
CONF_SITE_NAME = "site_name"
CONF_SCAN_INTERVAL = "scan_interval"
CONF_OWNER_VALUE_RATE = "owner_value_rate"
CONF_OWNER_SHARE_PERCENT = "owner_share_percent"
CONF_OWNER_PROJECTED_ANNUAL_EARNINGS_GBP = "owner_projected_annual_earnings_gbp"
CONF_SITE_PROJECTED_ANNUAL_EARNINGS_GBP = "site_projected_annual_earnings_gbp"

DEFAULT_BASE_URL = "https://dashboard.kirkhillcoop.org"
DEFAULT_CREATE_DASHBOARD = True
DEFAULT_ENABLE_PAYMENT_TRACKING = False
DEFAULT_SITE_NAME = "Kirk Hill Wind Farm"
DEFAULT_SCAN_INTERVAL = 60  # seconds between API polls
DEFAULT_OWNER_VALUE_RATE = 0.0
DEFAULT_OWNER_SHARE_PERCENT = 0.0
DEFAULT_OWNER_PROJECTED_ANNUAL_EARNINGS_GBP = 132.0
DEFAULT_SITE_PROJECTED_ANNUAL_EARNINGS_GBP = 0.0

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
TIMEFRAME_ORDER = ("yesterday", "today", "week", "month", "ytd", "year", "alltime")

PLATFORMS = ["sensor", "binary_sensor"]
