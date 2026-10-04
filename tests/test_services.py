"""Tests for services.py — domain-scoped service registration flag."""

from __future__ import annotations

import pytest

from custom_components.kirkhill_wind.const import DOMAIN
from custom_components.kirkhill_wind.services import (
    SERVICE_RELOAD_INTEGRATION,
    SERVICE_RESET_DASHBOARD,
    SERVICES_REGISTERED,
    async_setup_services,
    async_unload_services,
)

# Another installed integration (flight_price_tracker) uses this exact bare
# key in the same global hass.data namespace.
BARE_KEY = "services_registered"

EXPECTED_SERVICES = [
    (DOMAIN, SERVICE_RELOAD_INTEGRATION),
    (DOMAIN, SERVICE_RESET_DASHBOARD),
]


class TestServiceRegistrationFlag:
    """The registration flag must belong to this domain and nobody else."""

    @pytest.mark.asyncio
    async def test_registers_despite_another_integration_holding_the_bare_key(self, hass):
        """Someone else's flag must not gate, be consumed, or be cleared by us."""
        # The flag key is domain-scoped: a bare key is the bug being fixed.
        assert SERVICES_REGISTERED != BARE_KEY
        assert SERVICES_REGISTERED.startswith(DOMAIN)

        hass.data[BARE_KEY] = True  # flight_price_tracker's flag, set first

        await async_setup_services(hass)

        registered = [call.args[:2] for call in hass.services.async_register.call_args_list]
        assert registered == EXPECTED_SERVICES
        # Ours is set; theirs is untouched.
        assert hass.data[SERVICES_REGISTERED] is True
        assert hass.data[BARE_KEY] is True

    @pytest.mark.asyncio
    async def test_setup_is_idempotent(self, hass):
        """A second setup must not re-register the services."""
        await async_setup_services(hass)
        await async_setup_services(hass)

        assert hass.services.async_register.call_count == len(EXPECTED_SERVICES)

    @pytest.mark.asyncio
    async def test_unload_removes_its_own_services_only(self, hass):
        """Unload drops our services and our flag, leaving others' data alone."""
        hass.data[BARE_KEY] = True
        await async_setup_services(hass)
        hass.services.async_remove.reset_mock()

        await async_unload_services(hass)

        removed = [call.args for call in hass.services.async_remove.call_args_list]
        assert removed == EXPECTED_SERVICES
        # Our flag is cleared (the key stays, set to False) -- and only ours.
        assert hass.data[SERVICES_REGISTERED] is False
        assert hass.data[BARE_KEY] is True
