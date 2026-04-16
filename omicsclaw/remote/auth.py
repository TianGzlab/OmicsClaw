"""Bearer-token gate for remote control-plane routers.

Enabled when ``OMICSCLAW_REMOTE_AUTH_TOKEN`` is set to a non-empty value.
When unset (or whitespace-only) the gate is a no-op so local development
and single-user SSH-tunnel setups (the MVP-1 default) keep working.

The token is validated constant-time to avoid timing side-channels.
"""

from __future__ import annotations

import hmac
import os

from fastapi import Header, HTTPException, status

TOKEN_ENV = "OMICSCLAW_REMOTE_AUTH_TOKEN"


def _expected_token() -> str:
    return os.environ.get(TOKEN_ENV, "").strip()


async def require_bearer_token(
    authorization: str | None = Header(default=None),
) -> None:
    expected = _expected_token()
    if not expected:
        return
    if not authorization:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="missing bearer token",
            headers={"WWW-Authenticate": 'Bearer realm="omicsclaw-remote"'},
        )
    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not hmac.compare_digest(token.strip(), expected):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="invalid bearer token",
            headers={"WWW-Authenticate": 'Bearer realm="omicsclaw-remote"'},
        )
