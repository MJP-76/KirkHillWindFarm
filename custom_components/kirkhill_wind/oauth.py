"""Sign in with a Kirk Hill dashboard account instead of pasting an API key.

The dashboard publishes an OAuth 2.1 authorization-code flow with PKCE
(``oauth.md``) whose access token *is* the normal ``kh_live_*`` API key the
config flow used to ask for. So the token this flow returns is handed straight
to the existing code path as ``entry.data[CONF_API_KEY]``: nothing downstream
knows or cares how the key was obtained, and keys pasted by earlier users keep
working.

Three things the published flow expects that Home Assistant's OAuth helper does
not do for us:

1. **Dynamic client registration.** The redirect URI differs per install (and
   per browser host), so a ``client_id`` cannot sit in ``manifest.json``.
   ``POST /oauth/register`` is called once per redirect URI -- as ``oauth.md``
   asks ("register once, then store") -- and the result is kept in a Store, so
   a restart never registers the same URI again.
2. **Endpoint discovery.** ``oauth.md`` says to read
   ``/.well-known/oauth-authorization-server`` rather than hard-code endpoints.
   Discovered endpoints are cached alongside the client ids.
3. **No refresh token.** ``expires_in: 7776000`` is an *idle* window (the key
   dies after 90 days without a successful request), not a token lifetime, and
   the server issues no refresh token. We deliberately never build HA's
   ``OAuth2Session`` -- this integration polls with its own client straight from
   ``entry.data`` -- so there is no refresh path to fail at day 90. When the key
   really is dead the API answers 401 and the existing reauth flow takes over.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

import aiohttp
from homeassistant.core import HomeAssistant
from homeassistant.helpers.config_entry_oauth2_flow import (
    LocalOAuth2ImplementationWithPkce,
    async_get_redirect_uri,
    async_register_implementation,
)
from homeassistant.helpers.storage import Store

from .const import DEFAULT_BASE_URL, DOMAIN

_LOGGER = logging.getLogger(__name__)

TIMEOUT = aiohttp.ClientTimeout(total=20)

# oauth.md: applications should discover endpoints rather than hard-code them.
WELL_KNOWN_PATH = "/.well-known/oauth-authorization-server"
ENDPOINT_KEYS = ("authorization_endpoint", "token_endpoint", "registration_endpoint")

# The OAuth scope is fixed by oauth.md. The data permission (share / whole farm
# / both) is chosen on the consent screen and attached to the key by the server,
# so it never appears here.
OAUTH_SCOPE = "windfarm:read"

# Shown to the user on the dashboard's consent screen as the requesting app.
CLIENT_NAME = "Kirk Hill Wind Farm Home Assistant integration"

# Persisted through HA's Store, which owns the file under .storage. Nothing
# else in this integration writes it, and no secret lives in it: a public
# client has no client_secret, only the issued client_id.
STORAGE_KEY = f"{DOMAIN}.oauth_client"
STORAGE_VERSION = 1


class KirkHillOAuthError(Exception):
    """The dashboard's OAuth service could not be used right now."""


def _store(hass: HomeAssistant) -> Store:
    """Return the Store holding discovered endpoints and registered client ids."""
    return Store(hass, STORAGE_VERSION, STORAGE_KEY)


async def _async_discover_endpoints(session: aiohttp.ClientSession) -> dict[str, str]:
    """Read the authorization server metadata the dashboard publishes."""
    url = f"{DEFAULT_BASE_URL}{WELL_KNOWN_PATH}"
    try:
        async with session.get(url, timeout=TIMEOUT) as resp:
            if resp.status != 200:
                raise KirkHillOAuthError(
                    f"Authorization server metadata returned HTTP {resp.status}"
                )
            payload: Any = await resp.json()
    except KirkHillOAuthError:
        raise
    except (aiohttp.ClientError, asyncio.TimeoutError) as exc:
        raise KirkHillOAuthError(f"Could not read {url}: {exc}") from exc

    if not isinstance(payload, dict):
        raise KirkHillOAuthError("Authorization server metadata is not an object")
    missing = [key for key in ENDPOINT_KEYS if not payload.get(key)]
    if missing:
        raise KirkHillOAuthError(
            f"Authorization server metadata is missing: {', '.join(missing)}"
        )
    return {key: str(payload[key]) for key in ENDPOINT_KEYS}


async def _async_register_client(
    session: aiohttp.ClientSession, endpoints: dict[str, str], redirect_uri: str
) -> str:
    """Register this install's public client for one redirect URI."""
    payload = {
        "client_name": CLIENT_NAME,
        "redirect_uris": [redirect_uri],
        "grant_types": ["authorization_code"],
        "response_types": ["code"],
        "token_endpoint_auth_method": "none",
    }
    url = endpoints["registration_endpoint"]
    try:
        async with session.post(url, json=payload, timeout=TIMEOUT) as resp:
            if resp.status not in (200, 201):
                raise KirkHillOAuthError(
                    f"Client registration returned HTTP {resp.status}"
                )
            body: Any = await resp.json()
    except KirkHillOAuthError:
        raise
    except (aiohttp.ClientError, asyncio.TimeoutError) as exc:
        raise KirkHillOAuthError(f"Could not register with {url}: {exc}") from exc

    client_id = body.get("client_id") if isinstance(body, dict) else None
    if not client_id:
        raise KirkHillOAuthError("Client registration response has no client_id")
    return str(client_id)


async def async_get_implementation(
    hass: HomeAssistant, session: aiohttp.ClientSession
) -> KirkHillOAuthImplementation:
    """Return this install's implementation, registering it the first time.

    Keyed by redirect URI: Nabu Casa installs all resolve to my.home-assistant
    .io's fixed URI -- one registration shared by every such install -- while a
    plain LAN install registers per host it is reached on, and a host already
    seen never registers again.
    """
    try:
        redirect_uri = async_get_redirect_uri(hass)
    except RuntimeError as exc:
        # No request context (a flow started outside the frontend). The caller
        # offers the paste-an-API-key path instead of failing the whole flow.
        raise KirkHillOAuthError(f"Redirect URI unavailable: {exc}") from exc

    stored: Any = await _store(hass).async_load()
    data: dict[str, Any] = dict(stored) if isinstance(stored, dict) else {}
    changed = False

    endpoints = data.get("endpoints")
    if not endpoints:
        endpoints = await _async_discover_endpoints(session)
        data["endpoints"] = endpoints
        changed = True

    clients: dict[str, str] = dict(data.get("clients") or {})
    client_id = clients.get(redirect_uri)
    if not client_id:
        client_id = await _async_register_client(session, endpoints, redirect_uri)
        clients[redirect_uri] = client_id
        data["clients"] = clients
        changed = True

    if changed:
        await _store(hass).async_save(data)

    implementation = KirkHillOAuthImplementation(
        hass, redirect_uri, endpoints, client_id
    )
    async_register_implementation(hass, DOMAIN, implementation)
    return implementation


class KirkHillOAuthImplementation(LocalOAuth2ImplementationWithPkce):
    """HA's PKCE implementation, pinned to one registered redirect URI."""

    def __init__(
        self,
        hass: HomeAssistant,
        redirect_uri: str,
        endpoints: dict[str, str],
        client_id: str,
    ) -> None:
        """Build an implementation for an already-registered client."""
        super().__init__(
            hass,
            DOMAIN,
            client_id,
            endpoints["authorization_endpoint"],
            endpoints["token_endpoint"],
        )
        self._redirect_uri = redirect_uri

    @property
    def name(self) -> str:
        """Name shown if the flow ever has to offer a choice of implementation."""
        return "Kirk Hill dashboard account"

    @property
    def redirect_uri(self) -> str:
        """The exact URI we registered.

        Pinned rather than read from the request context again, so the
        authorize request, the state cookie and the token exchange all send the
        byte-identical value the dashboard matched at registration.
        """
        return self._redirect_uri

    @property
    def extra_authorize_data(self) -> dict[str, str]:
        """Ask for the read scope alongside the PKCE parameters."""
        return {"scope": OAUTH_SCOPE, **super().extra_authorize_data}

    async def async_generate_authorize_url(self, flow_id: str) -> str:
        """Mint a fresh PKCE verifier for every attempt.

        oauth.md: "Do not reuse these values between authorization attempts."
        The base class generates its code_verifier once in ``__init__``, so a
        cached implementation would otherwise replay the same challenge for the
        life of the process -- while the client_id, which *is* meant to be
        reused, stays in the Store.
        """
        self.code_verifier = self.generate_code_verifier()
        return await super().async_generate_authorize_url(flow_id)
