"""Config flow for the Kirk Hill Wind Farm integration."""
from __future__ import annotations

from typing import Any

import aiohttp
import voluptuous as vol
from homeassistant import config_entries
from homeassistant.core import callback
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
    CONF_SCAN_INTERVAL,
    CONF_SITE_NAME,
    DEFAULT_BASE_URL,
    DEFAULT_CREATE_DASHBOARD,
    DEFAULT_SCAN_INTERVAL,
    DEFAULT_SITE_NAME,
    DOMAIN,
    MAX_SCAN_INTERVAL,
    MIN_SCAN_INTERVAL,
)
from .exceptions import KirkHillAuthError, KirkHillConnectionError


class KirkHillWindConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for the Kirk Hill Wind Farm integration."""

    VERSION = 3

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
        except Exception:  # noqa: BLE001
            return {"base": "unknown"}
        return {}

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
                }
            ),
        )
