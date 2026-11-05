"""
API KEY AUTHENTICATION -- the "easy way" to add REAL auth to an A2A agent.
=============================================================================
One shared secret every caller must send in the `X-API-Key` header,
checked BEFORE the request ever reaches A2A's own routing. This plugs
into Starlette's standard `AuthenticationMiddleware` -- the exact same
extension point the a2a-sdk itself expects (see
`ServerCallContextBuilder` in `a2a/server/routes/common.py`, which
reads `request.scope['user']`/`request.auth`, both populated by this
middleware).

This is the SIMPLEST real scheme that exists (a single static key), not
the ONLY one A2A supports -- the real spec also allows OAuth2, OpenID
Connect, and mutual TLS, declared the same way (see
`agent_card_builder.py`). A single shared key is a reasonable first
step for a small number of trusted callers; a production system serving
many different outside clients would eventually want per-caller keys or
real OAuth2 instead of one key shared by everyone.

The Agent Card endpoint itself is deliberately left UNAUTHENTICATED --
a client has to be able to read the card (including which auth scheme
it needs) before it can possibly know how to authenticate.
"""

import hmac

from starlette.authentication import (
    AuthCredentials,
    AuthenticationBackend,
    AuthenticationError,
    SimpleUser,
)
from starlette.middleware.authentication import AuthenticationMiddleware
from starlette.requests import HTTPConnection
from starlette.responses import JSONResponse

API_KEY_HEADER = "X-API-Key"
_PUBLIC_PATH = "/.well-known/agent-card.json"

# The stand-in value shipped in .env.example / config.py's fallback. It is
# published in this repo, so it is not a secret -- refuse to start with it.
PLACEHOLDER_KEY = "PUT_YOUR_OWN_MADE_UP_SECRET_HERE"


def keys_match(provided: str, expected: str) -> bool:
    """Constant-time key comparison, shared by the agents and the catalog.

    compare_digest rather than `!=` so a wrong key takes the same time to
    reject no matter how many leading characters were right. Compared as
    UTF-8 bytes because compare_digest raises TypeError on non-ASCII str
    -- a client sending a non-ASCII key should get a clean 401, not a 500.
    """
    return hmac.compare_digest(provided.encode("utf-8"), expected.encode("utf-8"))


def require_real_key(expected_key: str) -> str:
    """Fails loudly at startup if AGENT_API_KEY was never configured.

    Without this, a missing .env silently falls back to the placeholder
    above -- a string committed to this repo -- so the agent would come up
    looking authenticated while accepting a publicly-known key. A
    misconfigured deploy should refuse to boot, not quietly serve."""
    if not expected_key or expected_key == PLACEHOLDER_KEY:
        raise RuntimeError(
            "AGENT_API_KEY is unset or still the placeholder. Set a real value in "
            ".env before starting an agent -- generate one with `openssl rand -hex 32`."
        )
    return expected_key


class ApiKeyBackend(AuthenticationBackend):
    """Rejects any request that doesn't send the correct shared key."""

    def __init__(self, expected_key: str):
        self._expected_key = require_real_key(expected_key)

    async def authenticate(self, conn: HTTPConnection):
        if conn.url.path == _PUBLIC_PATH:
            return AuthCredentials(["anonymous"]), SimpleUser("anonymous")

        provided_key = conn.headers.get(API_KEY_HEADER)
        if not provided_key or not keys_match(provided_key, self._expected_key):
            raise AuthenticationError(f"Missing or invalid {API_KEY_HEADER} header")

        return AuthCredentials(["authenticated"]), SimpleUser("api-key-client")


def _on_auth_error(conn: HTTPConnection, exc: AuthenticationError) -> JSONResponse:
    return JSONResponse({"error": str(exc)}, status_code=401)


def add_api_key_auth(app, expected_key: str) -> None:
    """Adds real API-key enforcement to an agent's FastAPI app. Call
    this once in server.py, right after creating `app`."""
    app.add_middleware(
        AuthenticationMiddleware,
        backend=ApiKeyBackend(expected_key),
        on_error=_on_auth_error,
    )
