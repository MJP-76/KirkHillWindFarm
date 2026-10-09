"""Tests for the dashboard sign-in path (OAuth 2.1 + PKCE) of the config flow.

The integration cannot tell a key obtained by sign-in from a pasted one -- both
end up as ``entry.data[CONF_API_KEY]`` and both are polled by the same client --
so what these tests protect is the claim that the two paths build the *same*
entry, plus the three things ``oauth.md`` asks of a client: register once per
redirect URI, discover the endpoints, and send a fresh PKCE verifier per attempt.

Nothing here touches the network or HA's ``.storage``: the session and the
Store are both fakes, and the redirect URI comes from loading the ``my``
component rather than from a browser request.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock
from urllib.parse import parse_qs, urlparse

import pytest

from custom_components.kirkhill_wind import config_flow, oauth
from custom_components.kirkhill_wind.const import (
    CONF_API_KEY,
    CONF_BASE_URL,
    CONF_CREATE_DASHBOARD,
    CONF_ENABLE_PAYMENT_TRACKING,
    CONF_SCAN_INTERVAL,
    CONF_SITE_NAME,
    DEFAULT_BASE_URL,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
)

# What async_get_redirect_uri returns once the "my" component is loaded, so no
# browser request has to be in context for the redirect URI to resolve.
REDIRECT_URI = "https://my.home-assistant.io/redirect/oauth"

ENDPOINTS = {
    "authorization_endpoint": "https://dashboard.kirkhillcoop.org/oauth/authorize",
    "token_endpoint": "https://dashboard.kirkhillcoop.org/oauth/token",
    "registration_endpoint": "https://dashboard.kirkhillcoop.org/oauth/register",
}
METADATA = {**ENDPOINTS, "issuer": "https://dashboard.kirkhillcoop.org"}

SETTINGS_KEYS = {
    CONF_SITE_NAME,
    CONF_SCAN_INTERVAL,
    CONF_CREATE_DASHBOARD,
    CONF_ENABLE_PAYMENT_TRACKING,
}


class FakeResponse:
    """An aiohttp response with only what the OAuth module reads."""

    def __init__(self, status: int, payload: dict) -> None:
        self.status = status
        self._payload = payload

    async def json(self) -> dict:
        return self._payload

    async def __aenter__(self) -> "FakeResponse":
        return self

    async def __aexit__(self, *exc_info) -> bool:
        return False


class FakeSession:
    """Answers discovery and registration; never leaves the process."""

    def __init__(self, *, metadata_status: int = 200, registration_status: int = 201,
                 registration_body: dict | None = None) -> None:
        self.get_calls: list[str] = []
        self.post_calls: list[tuple[str, dict]] = []
        self.metadata_status = metadata_status
        self.registration_status = registration_status
        self.registration_body = (
            registration_body
            if registration_body is not None
            else {"client_id": "mcp_client_from_server"}
        )

    def get(self, url: str, **kwargs) -> FakeResponse:
        self.get_calls.append(url)
        return FakeResponse(self.metadata_status, METADATA)

    def post(self, url: str, json: dict | None = None, **kwargs) -> FakeResponse:
        self.post_calls.append((url, json or {}))
        return FakeResponse(self.registration_status, self.registration_body)


class FakeStore:
    """Same interface as HA's Store, without writing a .storage file."""

    def __init__(self) -> None:
        self.data: dict | None = None
        self.saves = 0

    async def async_load(self) -> dict | None:
        return self.data

    async def async_save(self, data: dict) -> None:
        self.data = data
        self.saves += 1


def _make_flow(hass) -> config_flow.KirkHillWindConfigFlow:
    """Build a flow wired to mocks instead of a live flow manager."""
    flow = config_flow.KirkHillWindConfigFlow()
    flow.hass = hass
    flow.flow_id = "flow-1"
    flow.handler = DOMAIN
    flow.context = {"source": "user"}
    flow._async_current_entries = MagicMock(return_value=[])
    return flow


def _query(url: str, key: str) -> str:
    return parse_qs(urlparse(url).query)[key][0]


@pytest.fixture
def store(monkeypatch):
    fake = FakeStore()
    monkeypatch.setattr(oauth, "_store", lambda hass: fake)
    return fake


@pytest.fixture
def my_component(hass):
    hass.config.components.add("my")
    return hass


class TestMenu:
    """Sign-in is parked; the single-instance rule and the menu must survive."""

    @pytest.mark.asyncio
    async def test_signin_is_parked_so_the_form_shows_directly(self, hass):
        flow = _make_flow(hass)

        result = await flow.async_step_user()

        assert not config_flow.SIGN_IN_ENABLED, "parked on purpose, not by accident"
        assert result["type"] == "form"
        assert result["step_id"] == "manual", (
            "Setup must land on the working API-key form while sign-in is parked"
        )

    @pytest.mark.asyncio
    async def test_enabling_signin_restores_the_menu(self, hass, monkeypatch):
        """Re-enabling must bring both paths back, not a half-working flow."""
        monkeypatch.setattr(config_flow, "SIGN_IN_ENABLED", True)
        flow = _make_flow(hass)

        result = await flow.async_step_user()

        assert result["type"] == "menu"
        assert set(result["menu_options"]) == {"oauth2", "manual"}

    @pytest.mark.asyncio
    async def test_single_instance_rule_still_applies(self, hass):
        flow = _make_flow(hass)
        flow._async_current_entries = MagicMock(return_value=[MagicMock()])

        result = await flow.async_step_user()

        assert result["type"] == "abort"
        assert result["reason"] == "single_instance_allowed"


class TestManualPath:
    """The paste-an-API-key path must behave exactly as it did before OAuth."""

    @pytest.mark.asyncio
    async def test_builds_the_entry_it_always_built(self, hass):
        flow = _make_flow(hass)
        flow._validate_api_key = AsyncMock(return_value={})

        result = await flow.async_step_manual(
            {
                CONF_API_KEY: "kirk_key_pasted",
                CONF_SITE_NAME: "My Farm",
                CONF_CREATE_DASHBOARD: False,
                CONF_ENABLE_PAYMENT_TRACKING: True,
            }
        )

        assert result["type"] == "create_entry"
        # Rule 2: entry.data is connection only.
        assert set(result["data"]) == {CONF_API_KEY, CONF_BASE_URL}
        assert result["data"] == {
            CONF_API_KEY: "kirk_key_pasted",
            CONF_BASE_URL: DEFAULT_BASE_URL,
        }
        # Rule 1: options must name every key -- HA replaces the mapping wholesale.
        assert set(result["options"]) == SETTINGS_KEYS
        assert result["options"][CONF_SCAN_INTERVAL] == DEFAULT_SCAN_INTERVAL
        assert result["options"][CONF_SITE_NAME] == "My Farm"
        assert result["options"][CONF_CREATE_DASHBOARD] is False
        assert CONF_API_KEY not in result["options"]

    @pytest.mark.asyncio
    async def test_rejected_key_reports_the_error(self, hass):
        flow = _make_flow(hass)
        flow._validate_api_key = AsyncMock(return_value={"base": "auth_failed"})

        result = await flow.async_step_manual({CONF_API_KEY: "nope"})

        assert result["type"] == "form"
        assert result["errors"] == {"base": "auth_failed"}


class TestRegistration:
    """oauth.md: register once per redirect URI, discover the endpoints."""

    @pytest.mark.asyncio
    async def test_registers_once_then_reuses_the_client_id(self, hass, my_component, store):
        session = FakeSession()

        first = await oauth.async_get_implementation(hass, session)
        second = await oauth.async_get_implementation(hass, session)

        assert len(session.post_calls) == 1, (
            "Registering again on the next attempt is exactly what oauth.md "
            "forbids ('Do not create a new registration for every login')."
        )
        assert len(session.get_calls) == 1, "discovered endpoints must be cached too"

        url, payload = session.post_calls[0]
        assert url == ENDPOINTS["registration_endpoint"]
        assert payload["redirect_uris"] == [REDIRECT_URI]
        assert payload["token_endpoint_auth_method"] == "none"
        assert payload["grant_types"] == ["authorization_code"]
        assert payload["response_types"] == ["code"]

        assert first.client_id == second.client_id == "mcp_client_from_server"
        assert first.redirect_uri == REDIRECT_URI, "the registered URI must be the one used"
        assert store.data["clients"][REDIRECT_URI] == "mcp_client_from_server"
        assert store.data["endpoints"] == ENDPOINTS

    @pytest.mark.asyncio
    async def test_discovery_failure_is_reported_not_cached(self, hass, my_component, store):
        session = FakeSession(metadata_status=503)

        with pytest.raises(oauth.KirkHillOAuthError):
            await oauth.async_get_implementation(hass, session)

        assert store.saves == 0, "a failed setup must not be remembered as a working one"

    @pytest.mark.asyncio
    async def test_registration_rejection_is_reported(self, hass, my_component, store):
        session = FakeSession(
            registration_status=400, registration_body={"error": "invalid_client_name"}
        )

        with pytest.raises(oauth.KirkHillOAuthError):
            await oauth.async_get_implementation(hass, session)

        assert store.saves == 0

    @pytest.mark.asyncio
    async def test_missing_redirect_uri_is_reported(self, hass, store):
        # No "my" component and no browser request -> no redirect URI to register.
        session = FakeSession()

        with pytest.raises(oauth.KirkHillOAuthError):
            await oauth.async_get_implementation(hass, session)

        assert session.post_calls == []


class TestAuthorizeUrl:
    """The authorize request must carry the scope, PKCE and the registered URI."""

    @pytest.mark.asyncio
    async def test_url_carries_scope_pkce_and_the_registered_redirect(self, hass, my_component):
        implementation = oauth.KirkHillOAuthImplementation(
            hass, REDIRECT_URI, ENDPOINTS, "mcp_client_test"
        )

        url = await implementation.async_generate_authorize_url("flow-1")

        assert _query(url, "client_id") == "mcp_client_test"
        assert _query(url, "response_type") == "code"
        assert _query(url, "scope") == "windfarm:read"
        assert _query(url, "code_challenge_method") == "S256"
        assert _query(url, "redirect_uri") == REDIRECT_URI
        assert implementation.redirect_uri == REDIRECT_URI

    @pytest.mark.asyncio
    async def test_each_attempt_gets_a_fresh_pkce_verifier(self, hass, my_component):
        implementation = oauth.KirkHillOAuthImplementation(
            hass, REDIRECT_URI, ENDPOINTS, "mcp_client_test"
        )

        first = await implementation.async_generate_authorize_url("flow-1")
        second = await implementation.async_generate_authorize_url("flow-2")

        assert _query(first, "code_challenge") != _query(second, "code_challenge"), (
            "oauth.md: 'Do not reuse these values between authorization "
            "attempts' -- the base class only mints a verifier once."
        )


class TestOAuthEntry:
    """The sign-in path must land on the very same entry shape as the paste path."""

    @pytest.mark.asyncio
    async def test_token_becomes_the_same_entry(self, hass):
        flow = _make_flow(hass)
        flow._validate_api_key = AsyncMock(return_value={})

        form = await flow.async_oauth_create_entry(
            {
                "auth_implementation": DOMAIN,
                "token": {
                    "access_token": "kh_live_from_oauth",
                    "expires_in": 7776000,
                    "expires_at": 1.0,
                },
            }
        )
        assert form["type"] == "form"
        assert form["step_id"] == "settings"

        result = await flow.async_step_settings(
            {
                CONF_SITE_NAME: "Kirk Hill",
                CONF_CREATE_DASHBOARD: True,
                CONF_ENABLE_PAYMENT_TRACKING: False,
            }
        )

        assert result["type"] == "create_entry"
        assert set(result["data"]) == {CONF_API_KEY, CONF_BASE_URL}, (
            "entry.data is connection only (rule 2): the OAuth token blob and "
            "auth_implementation must not leak in -- the integration reads the "
            "key and nothing else, and never builds an OAuth2Session."
        )
        assert result["data"][CONF_API_KEY] == "kh_live_from_oauth"
        assert "token" not in result["data"]
        assert "auth_implementation" not in result["data"]
        # Rule 1: identical, complete options mapping to the paste path.
        assert set(result["options"]) == SETTINGS_KEYS
        assert result["options"][CONF_SITE_NAME] == "Kirk Hill"
        assert result["options"][CONF_SCAN_INTERVAL] == DEFAULT_SCAN_INTERVAL

    @pytest.mark.asyncio
    async def test_key_that_cannot_read_the_api_aborts(self, hass):
        flow = _make_flow(hass)
        flow._validate_api_key = AsyncMock(return_value={"base": "auth_failed"})

        result = await flow.async_oauth_create_entry(
            {"token": {"access_token": "kh_live_dead"}}
        )

        assert result["type"] == "abort"
        assert result["reason"] == "oauth_key_invalid", (
            "A key revoked mid-flow must not produce an entry that starts out dead."
        )

    @pytest.mark.asyncio
    async def test_missing_access_token_aborts(self, hass):
        flow = _make_flow(hass)

        result = await flow.async_oauth_create_entry({"token": {}})

        assert result["type"] == "abort"
        assert result["reason"] == "oauth_error"

    @pytest.mark.asyncio
    async def test_registration_failure_points_at_the_manual_path(
        self, hass, monkeypatch
    ):
        flow = _make_flow(hass)
        monkeypatch.setattr(
            config_flow, "async_get_clientsession", MagicMock(return_value=object())
        )
        monkeypatch.setattr(
            config_flow,
            "async_get_implementation",
            AsyncMock(side_effect=config_flow.KirkHillOAuthError("boom")),
        )

        result = await flow.async_step_oauth2()

        assert result["type"] == "form"
        assert result["step_id"] == "oauth2"
        assert result["errors"] == {"base": "oauth_unavailable"}, (
            "The paste-an-API-key path is the fallback; the flow must explain "
            "why sign-in is unavailable rather than dead-ending."
        )


class TestAbortDiagnostics:
    """The sign-in abort must quote the API, not just say "could not be used"."""

    @pytest.mark.asyncio
    async def test_abort_carries_the_underlying_reason(self, hass):
        flow = _make_flow(hass)
        flow._validate_api_key = AsyncMock(return_value={"base": "auth_failed"})
        flow._validation_detail = "Invalid or missing API key: The API key is not valid."

        result = await flow.async_oauth_create_entry(
            {"token": {"access_token": "kh_live_doomed"}}
        )

        assert result["type"] == "abort"
        assert result["reason"] == "oauth_key_invalid"
        assert "not valid" in result["description_placeholders"]["detail"], (
            "Without the placeholder the user sees a reason-less sentence and "
            "the log is the only place the truth lives."
        )

    @pytest.mark.asyncio
    async def test_abort_falls_back_when_no_detail_exists(self, hass):
        flow = _make_flow(hass)
        flow._validate_api_key = AsyncMock(return_value={"base": "cannot_connect"})
        flow._validation_detail = ""

        result = await flow.async_oauth_create_entry(
            {"token": {"access_token": "kh_live_doomed"}}
        )

        assert result["type"] == "abort"
        assert result["description_placeholders"]["detail"]

    @pytest.mark.asyncio
    async def test_abort_reports_the_key_shape_but_not_the_key(self, hass):
        flow = _make_flow(hass)
        flow._validate_api_key = AsyncMock(return_value={"base": "auth_failed"})
        flow._validation_detail = (
            "Invalid or missing API key: The API key is not valid."
        )

        result = await flow.async_oauth_create_entry(
            {"token": {"access_token": "kh_live_supersecret9999"}}
        )

        detail = result["description_placeholders"]["detail"]
        assert "The API key is not valid." in detail, "the API's own words must stay"
        assert "Key we sent:" in detail
        assert "matches the kh_live_ API-key format" in detail
        assert "supersecret9999" not in detail, "never echo the key back"
