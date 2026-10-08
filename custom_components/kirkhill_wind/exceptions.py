"""Exceptions for the Kirk Hill Wind Farm integration."""


class KirkHillApiError(Exception):
    """Base exception for all Kirk Hill API errors."""


class KirkHillAuthError(KirkHillApiError):
    """Raised when the API returns 401 Unauthorised."""


class KirkHillConnectionError(KirkHillApiError):
    """Raised when the API cannot be reached (network / timeout)."""


class KirkHillPermissionError(KirkHillApiError):
    """Raised when the API returns 403 Forbidden.

    The key is valid but its data permission (share / whole farm / both) does not
    cover what was requested. Deliberately *not* a ``KirkHillAuthError``: a 401
    means "this key is dead" and must start re-auth, while a 403 means "this key
    may read less than the integration needs" -- re-entering the same key would
    not help. So setup rejects it with its own message, and at runtime it falls
    into the ordinary keep-last-known-data path instead of a reauth loop.
    """
