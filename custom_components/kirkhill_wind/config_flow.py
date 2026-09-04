"""Config flow for the Kirk Hill Wind Farm integration."""
from __future__ import annotations

import logging
from typing import Any

import aiohttp
import voluptuous as vol
from homeassistant import config_entries
from homeassistant.core import HomeAssistant, callback
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers.selector import (
    TextSelector,
    TextSelectorConfig,
    TextSelectorType,
)

from .api import KirkHillApiClient
from .const import (
    CONF_API_KEY,
    CONF_BASE_URL,
    CONF_CREATE_DASHBOARD,
    CONF_ENABLE_PAYMENT_TRACKING,
    CONF_GRAPH_HOURS,
    CONF_OWNER_PROJECTED_ANNUAL_EARNINGS_GBP,
    CONF_SCAN_INTERVAL,
    CONF_SITE_NAME,
    CONF_SITE_PROJECTED_ANNUAL_EARNINGS_GBP,
    DEFAULT_BASE_URL,
    DEFAULT_CREATE_DASHBOARD,
    DEFAULT_ENABLE_PAYMENT_TRACKING,
    DEFAULT_GRAPH_HOURS,
    DEFAULT_OWNER_PROJECTED_ANNUAL_EARNINGS_GBP,
    DEFAULT_SCAN_INTERVAL,
    DEFAULT_SITE_NAME,
    DEFAULT_SITE_PROJECTED_ANNUAL_EARNINGS_GBP,
    DOMAIN,
    MAX_SCAN_INTERVAL,
    MIN_SCAN_INTERVAL,
)
from .exceptions import KirkHillAuthError, KirkHillConnectionError

_LOGGER = logging.getLogger(__name__)


class KirkHillWindConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for the Kirk Hill Wind Farm integration."""

    VERSION = 4

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle the initial step: API key, site name, and dashboard choice."""
        if self._async_current_entries():
            return self.async_abort(reason="single_instance_allowed")

        errors: dict[str, str] = {}

        if user_input is not None:
            errors = await self._validate_api_key(
                user_input[CONF_API_KEY],
                DEFAULT_BASE_URL,
            )
            if not errors:
                return self.async_create_entry(
                    title=user_input.get(CONF_SITE_NAME, DEFAULT_SITE_NAME),
                    data={
                        CONF_API_KEY: user_input[CONF_API_KEY],
                        CONF_BASE_URL: DEFAULT_BASE_URL,
                        CONF_CREATE_DASHBOARD: user_input.get(
                            CONF_CREATE_DASHBOARD, DEFAULT_CREATE_DASHBOARD
                        ),
                        CONF_ENABLE_PAYMENT_TRACKING: user_input.get(
                            CONF_ENABLE_PAYMENT_TRACKING,
                            DEFAULT_ENABLE_PAYMENT_TRACKING,
                        ),
                        CONF_OWNER_PROJECTED_ANNUAL_EARNINGS_GBP: user_input.get(
                            CONF_OWNER_PROJECTED_ANNUAL_EARNINGS_GBP,
                            DEFAULT_OWNER_PROJECTED_ANNUAL_EARNINGS_GBP,
                        ),
                        CONF_SITE_PROJECTED_ANNUAL_EARNINGS_GBP: user_input.get(
                            CONF_SITE_PROJECTED_ANNUAL_EARNINGS_GBP,
                            DEFAULT_SITE_PROJECTED_ANNUAL_EARNINGS_GBP,
                        ),
                        CONF_SITE_NAME: user_input.get(CONF_SITE_NAME, DEFAULT_SITE_NAME),
                        CONF_SCAN_INTERVAL: DEFAULT_SCAN_INTERVAL,
                    },
                )

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_API_KEY): TextSelector(
                        TextSelectorConfig(type=TextSelectorType.PASSWORD)
                    ),
                    vol.Optional(
                        CONF_SITE_NAME, default=DEFAULT_SITE_NAME
                    ): str,
                    vol.Optional(
                        CONF_CREATE_DASHBOARD, default=DEFAULT_CREATE_DASHBOARD
                    ): bool,
                    vol.Optional(
                        CONF_ENABLE_PAYMENT_TRACKING,
                        default=DEFAULT_ENABLE_PAYMENT_TRACKING,
                    ): bool,
                    vol.Optional(
                        CONF_OWNER_PROJECTED_ANNUAL_EARNINGS_GBP,
                        default=DEFAULT_OWNER_PROJECTED_ANNUAL_EARNINGS_GBP,
                    ): vol.All(vol.Coerce(float), vol.Range(min=0)),
                    vol.Optional(
                        CONF_SITE_PROJECTED_ANNUAL_EARNINGS_GBP,
                        default=DEFAULT_SITE_PROJECTED_ANNUAL_EARNINGS_GBP,
                    ): vol.All(vol.Coerce(float), vol.Range(min=0)),
                }
            ),
            errors=errors,
        )

    async def _validate_api_key(
        self, api_key: str, base_url: str
    ) -> dict[str, str]:
        """Return an errors dict, or empty dict on success."""
        client = KirkHillApiClient(api_key=api_key, base_url=base_url)
        try:
            async with aiohttp.ClientSession() as session:
                await client.test(session)
        except KirkHillAuthError:
            return {"base": "auth_failed"}
        except KirkHillConnectionError:
            return {"base": "cannot_connect"}
        except Exception as exc:  # noqa: BLE001
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

    @classmethod
    async def async_migrate_entry(
        cls, hass: HomeAssistant, config_entry: config_entries.ConfigEntry
    ) -> bool:
        """Migrate config entries to the current version."""
        if config_entry.version == cls.VERSION:
            return True

        data = dict(config_entry.data)

        if config_entry.version < 3:
            # Version 3 introduced the base_url field so users can target a
            # non-default Kirk Hill dashboard instance.
            data.setdefault(CONF_BASE_URL, DEFAULT_BASE_URL)

        if config_entry.version < 4:
            # Version 4 removed the redundant owner_share_percent (now derived
            # from the API's capacity_watts ratio) and the unused legacy
            # owner_value_rate field.
            data.pop("owner_share_percent", None)
            data.pop("owner_value_rate", None)

        config_entry.data = data
        config_entry.version = cls.VERSION
        return True


class KirkHillWindOptionsFlow(config_entries.OptionsFlow):
    """Handle options: adjust the polling interval post-setup."""

    def __init__(self, config_entry: config_entries.ConfigEntry) -> None:
        self._config_entry = config_entry

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Manage the options."""
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        current = {**self._config_entry.data, **self._config_entry.options}
        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        CONF_SCAN_INTERVAL,
                        default=current.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL),
                    ): vol.All(
                        int, vol.Range(min=MIN_SCAN_INTERVAL, max=MAX_SCAN_INTERVAL)
                    ),
                    vol.Required(
                        CONF_CREATE_DASHBOARD,
                        default=current.get(
                            CONF_CREATE_DASHBOARD,
                            DEFAULT_CREATE_DASHBOARD,
                        ),
                    ): bool,
                    vol.Required(
                        CONF_ENABLE_PAYMENT_TRACKING,
                        default=current.get(
                            CONF_ENABLE_PAYMENT_TRACKING,
                            DEFAULT_ENABLE_PAYMENT_TRACKING,
                        ),
                    ): bool,
                    vol.Required(
                        CONF_GRAPH_HOURS,
                        default=current.get(CONF_GRAPH_HOURS, DEFAULT_GRAPH_HOURS),
                    ): vol.All(int, vol.Range(min=1, max=168)),
                    vol.Required(
                        CONF_OWNER_PROJECTED_ANNUAL_EARNINGS_GBP,
                        default=current.get(
                            CONF_OWNER_PROJECTED_ANNUAL_EARNINGS_GBP,
                            DEFAULT_OWNER_PROJECTED_ANNUAL_EARNINGS_GBP,
                        ),
                    ): vol.All(vol.Coerce(float), vol.Range(min=0)),
                    vol.Required(
                        CONF_SITE_PROJECTED_ANNUAL_EARNINGS_GBP,
                        default=current.get(
                            CONF_SITE_PROJECTED_ANNUAL_EARNINGS_GBP,
                            DEFAULT_SITE_PROJECTED_ANNUAL_EARNINGS_GBP,
                        ),
                    ): vol.All(vol.Coerce(float), vol.Range(min=0)),
                }
            ),
        )
