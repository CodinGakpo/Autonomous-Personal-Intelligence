"""Bearer-token auth for the brain service, sharing console/backend's JWT format.

Stateless: verifies the token's signature + expiry via `security.tokens.decode_token` and
trusts the embedded user id — this service never talks to Postgres, so it can't re-check
`is_active` the way console/backend's own `get_current_user` does. A deactivated user's token
therefore stays valid here until it naturally expires (8h TTL). Both processes must be started
with the same `OPS_SECRET_KEY` env var for tokens issued by console/backend's `/auth/login` to
verify here.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends, Header, HTTPException, status

from security.tokens import decode_token, get_secret_key


def get_current_user_id(authorization: Annotated[str, Header()] = "") -> int:
    scheme, _, token = authorization.partition(" ")
    user_id = decode_token(token, get_secret_key()) if scheme.lower() == "bearer" else None
    if user_id is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Authentication required")
    return user_id


CurrentUser = Annotated[int, Depends(get_current_user_id)]
