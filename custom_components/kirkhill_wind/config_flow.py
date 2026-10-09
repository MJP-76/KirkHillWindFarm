"""Config flow for the Kirk Hill Wind Farm integration."""
from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.core import callback
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers import config_entry_oauth2_flow
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.selector import (
    TextSelector,
    TextSelectorConfig,
    TextSelectorType,
)

from .api import KirkHillApiClient, describe_key
from .const import (
    CONF_API_KEY,
    CONF_BASE_URL,
    CONF_CREATE_DASHBOARD,
    CONF_ENABLE_PAYMENT_TRACKING,
    CONF_SCAN_INTERVAL,
    CONF_SITE_NAME,
    DEFAULT_BASE_URL,
    DEFAULT_CREATE_DASHBOARD,
    DEFAULT_ENABLE_PAYMENT_TRACKING,
    DEFAULT_SCAN_INTERVAL,
    DEFAULT_SITE_NAME,
    DOMAIN,
    MAX_SCAN_INTERVAL,
    MIN_SCAN_INTERVAL,
)
from .exceptions import (
    KirkHillAuthError,
    KirkHillConnectionError,
    KirkHillPermissionError,
)
from .oauth import KirkHillOAuthError, async_get_implementation
from .settings import form_defaults, merge_options

_LOGGER = logging.getLogger(__name__)

# The optional settings both sign-in paths offer. One definition on purpose:
# the OAuth path and the paste path must start an entry with the same options,
# or the two entry shapes would drift apart silently.
SETTINGS_FIELDS: dict[Any, Any] = {
    vol.Optional(CONF_SITE_NAME, default=DEFAULT_SITE_NAME): str,
    vol.Optional(CONF_CREATE_DASHBOARD, default=DEFAULT_CREATE_DASHBOARD): bool,
    vol.Optional(
        CONF_ENABLE_PAYMENT_TRACKING, default=DEFAULT_ENABLE_PAYMENT_TRACKING
    ): bool,
}


# Dashboard sign-in is PARKED, not deleted.
#
# The dashboard's token endpoint issues a 56-character kh_live_ key -- the same
# length and format as a working key -- that /api/v1/* then rejects with
# 401 "The API key is not valid." Reproduced across several attempts over
# several hours; the integration passes the value through byte for byte
# (access_token -> strip() -> Authorization header), so the fault is server-side
# key activation, upstream of us. Offering it would send every new user into a
# dead end, so setup goes straight to the API-key form instead.
#
# Everything else stays live: oauth.py, describe_key(), the permission gate and
# the OAuth tests all still run in CI, so nothing rots while parked. Flip this
# to True -- and revert the docs note -- once the dashboard team confirms
# OAuth-issued keys are accepted.
SIGN_IN_ENABLED = False


class KirkHillWindConfigFlow(
    config_entry_oauth2_flow.AbstractOAuth2FlowHandler, domain=DOMAIN
):
    """Handle a config flow for the Kirk Hill Wind Farm integration.

    The OAuth inheritance gives the dashboard sign-in Home Assistant's PKCE,
    redirect and state plumbing. The paste-an-API-key path is the original one,
    unchanged, so existing users and any install that cannot use OAuth still
    work exactly as before.
    """

    # Not implied by the domain= kwarg (that only registers the handler): the
    # OAuth base's __init__ refuses to build an instance whose DOMAIN is unset.
    DOMAIN = DOMAIN
    VERSION = 9

    # Set by async_oauth_create_entry and consumed by async_step_settings: the
    # token exchange hands over the key, the settings step builds the entry.
    _oauth_api_key: str | None = None

    # Why the last validation failed, verbatim from the API. Kept on the flow
    # so the sign-in abort can quote it; _validate_api_key returns only the
    # translation key, which by itself hides 401 vs 429 vs a timeout.
    _validation_detail: str = ""

    @property
    def logger(self) -> logging.Logger:
        """Return the logger (abstract on the OAuth base class)."""
        return _LOGGER

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Offer sign-in and paste-a-key -- or, while sign-in is parked, just paste.

        Picking a menu option makes Home Assistant jump straight to that step
        with ``user_input=None``, so this method only ever decides *whether* to
        show a menu.
        """
        if self._async_current_entries():
            return self.async_abort(reason="single_instance_allowed")
        if not SIGN_IN_ENABLED:
            # Parked: offering a sign-in the API currently rejects would be a
            # dead end. The step_id stays "manual", so the strings this form
            # renders are already the right ones -- no i18n change needed.
            return await self.async_step_manual()
        return self.async_show_menu(step_id="user", menu_options=["oauth2", "manual"])

    async def async_step_manual(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle the original API key form, unchanged."""
        if self._async_current_entries():
            return self.async_abort(reason="single_instance_allowed")

        errors: dict[str, str] = {}
        if user_input is not None:
            errors = await self._validate_api_key(
                user_input[CONF_API_KEY],
                DEFAULT_BASE_URL,
            )
            if not errors:
                return self._async_create_entry(user_input[CONF_API_KEY], user_input)

        return self.async_show_form(
            step_id="manual",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_API_KEY): TextSelector(
                        TextSelectorConfig(type=TextSelectorType.PASSWORD)
                    ),
                    **SETTINGS_FIELDS,
                }
            ),
            errors=errors,
        )

    async def async_step_oauth2(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Sign in with the Kirk Hill dashboard account (OAuth 2.1 + PKCE)."""
        try:
            await async_get_implementation(
                self.hass, async_get_clientsession(self.hass)
            )
        except KirkHillOAuthError as exc:
            # Endpoint discovery or client registration failed. Say why and
            # leave the paste-an-API-key path on offer rather than dead-ending
            # the flow; submitting the form retries.
            _LOGGER.warning("Kirk Hill OAuth setup failed: %s", exc)
            return self.async_show_form(
                step_id="oauth2",
                data_schema=vol.Schema({}),
                errors={"base": "oauth_unavailable"},
            )
        return await self.async_step_pick_implementation()

    async def async_oauth_create_entry(self, data: dict) -> FlowResult:
        """Turn the OAuth token into an entry shaped like the paste path's."""
        token = data.get("token") or {}
        api_key = token.get("access_token")
        if not api_key:
            return self.async_abort(reason="oauth_error")
        # The key just came from the dashboard, but confirm it reads the API:
        # a key revoked mid-flow must not produce an entry that starts out dead.
        errors = await self._validate_api_key(api_key, DEFAULT_BASE_URL)
        if errors:
            # Quote the API's own words. "Could not be used" with no reason
            # left nothing to act on -- the detail is what tells a reporter
            # apart from a dashboard-side fault.
            detail = self._validation_detail or "no reason was returned"
            if errors.get("base") == "auth_failed":
                # 401 on a key the dashboard had just issued is either the
                # dashboard rejecting its own key or us sending the wrong
                # bytes. Length and format -- never the key -- settle it.
                shape = describe_key(api_key)
                _LOGGER.warning(
                    "Kirk Hill sign-in: API rejected the issued key (%s); it said: %s",
                    shape,
                    detail,
                )
                detail = f"{detail} Key we sent: {shape}."
            if errors.get("base") == "permission_required":
                # Repeating sign-in with the same narrow consent fails again,
                # so say which consent option is needed rather than "invalid".
                return self.async_abort(
                    reason="oauth_permission_denied",
                    description_placeholders={"detail": detail},
                )
            return self.async_abort(
                reason="oauth_key_invalid",
                description_placeholders={"detail": detail},
            )
        self._oauth_api_key = api_key
        return await self.async_step_settings()

    async def async_step_settings(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Collect the optional settings the paste form offers, after sign-in."""
        if self._oauth_api_key is None:
            return self.async_abort(reason="oauth_error")
        if user_input is not None:
            return self._async_create_entry(self._oauth_api_key, user_input)
        return self.async_show_form(
            step_id="settings",
            data_schema=vol.Schema(dict(SETTINGS_FIELDS)),
        )

    def _async_create_entry(self, api_key: str, settings: dict[str, Any]) -> FlowResult:
        """Create the config entry.

        ``data`` carries connection details only (AGENTS.md rule 2). The
        ``options`` mapping is the complete initial options dict, so it names
        every key the options flow and the number entities read -- Home
        Assistant replaces that mapping wholesale, and the OAuth path must not
        hand over a shorter one than the paste path did.
        """
        return self.async_create_entry(
            title=settings.get(CONF_SITE_NAME, DEFAULT_SITE_NAME),
            data={
                CONF_API_KEY: api_key,
                CONF_BASE_URL: DEFAULT_BASE_URL,
            },
            options={
                CONF_SITE_NAME: settings.get(CONF_SITE_NAME, DEFAULT_SITE_NAME),
                CONF_SCAN_INTERVAL: DEFAULT_SCAN_INTERVAL,
                CONF_CREATE_DASHBOARD: settings.get(
                    CONF_CREATE_DASHBOARD, DEFAULT_CREATE_DASHBOARD
                ),
                CONF_ENABLE_PAYMENT_TRACKING: settings.get(
                    CONF_ENABLE_PAYMENT_TRACKING, DEFAULT_ENABLE_PAYMENT_TRACKING
                ),
            },
        )

    async def _validate_api_key(
        self, api_key: str, base_url: str
    ) -> dict[str, str]:
        """Return an errors dict, or empty dict on success."""
        self._validation_detail = ""
        client = KirkHillApiClient(api_key=api_key, base_url=base_url)
        try:
            # Reuse HA's shared session rather than a throwaway one per attempt.
            await client.test(async_get_clientsession(self.hass))
        except KirkHillAuthError as exc:
            # Logged, not just returned: before this, a rejected key produced
            # an opaque one-line abort and left nothing in the log to diagnose.
            self._validation_detail = str(exc)
            _LOGGER.warning("Kirk Hill API rejected the key during validation: %s", exc)
            return {"base": "auth_failed"}
        except KirkHillPermissionError as exc:
            # A different message from auth_failed on purpose: the key is
            # fine, it just may not read everything, and re-entering the same
            # key would fail the same way.
            self._validation_detail = str(exc)
            _LOGGER.warning("Kirk Hill API key lacks permission: %s", exc)
            return {"base": "permission_required"}
        except KirkHillConnectionError as exc:
            self._validation_detail = str(exc)
            _LOGGER.warning("Kirk Hill API unreachable during validation: %s", exc)
            return {"base": "cannot_connect"}
        except Exception as exc:  # noqa: BLE001
            self._validation_detail = str(exc)
            _LOGGER.exception("Unexpected error validating Kirk Hill API key: %s", exc)
            return {"base": "unknown"}
        return {}

    async def async_step_reauth(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle reauthentication when the API key is no longer valid."""
        entry_id = self.context.get("entry_id")
        entry = self.hass.config_entries.async_get_entry(entry_id) if entry_id else None
        if entry is None:
            return self.async_abort(reason="reauth_failed")
        errors: dict[str, str] = {}

        if user_input is not None:
            errors = await self._validate_api_key(
                user_input[CONF_API_KEY],
                entry.data.get(CONF_BASE_URL, DEFAULT_BASE_URL),
            )
            if not errors:
                data = dict(entry.data)
                data[CONF_API_KEY] = user_input[CONF_API_KEY]
                self.hass.config_entries.async_update_entry(entry, data=data)
                return self.async_abort(reason="reauth_successful")

        return self.async_show_form(
            step_id="reauth",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_API_KEY): TextSelector(
                        TextSelectorConfig(type=TextSelectorType.PASSWORD)
                    ),
                }
            ),
            errors=errors,
        )

    @staticmethod
    @callback
    def async_get_options_flow(
        config_entry: config_entries.ConfigEntry,
    ) -> KirkHillWindOptionsFlow:
        """Return the options flow."""
        return KirkHillWindOptionsFlow(config_entry)


class KirkHillWindOptionsFlow(config_entries.OptionsFlow):
    """Handle options: adjust the polling interval post-setup."""

    def __init__(self, config_entry: config_entries.ConfigEntry) -> None:
        self._config_entry = config_entry

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Manage the options."""
        if user_input is not None:
            # Home Assistant assigns this mapping over entry.options wholesale,
            # so passing only the form fields would delete every setting the
            # form does not show -- including the two prices the number
            # entities persist there. Merge instead of replace.
            return self.async_create_entry(
                title="",
                data=merge_options(dict(self._config_entry.options), user_input),
            )

        current = form_defaults(self._config_entry)
        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        CONF_SCAN_INTERVAL, default=current[CONF_SCAN_INTERVAL]
                    ): vol.All(
                        int, vol.Range(min=MIN_SCAN_INTERVAL, max=MAX_SCAN_INTERVAL)
                    ),
                    vol.Required(
                        CONF_CREATE_DASHBOARD, default=current[CONF_CREATE_DASHBOARD]
                    ): bool,
                    vol.Required(
                        CONF_ENABLE_PAYMENT_TRACKING,
                        default=current[CONF_ENABLE_PAYMENT_TRACKING],
                    ): bool,
                }
            ),
        )
