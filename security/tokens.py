"""Shared stateless-JWT verification, usable by any service without pulling in the others.

`console.backend` issues tokens (see `console/backend/security.py`'s `create_token`, which stays
there since only that service handles login/passwords); this module owns *decoding* them so
`brain/viz_server.py` can verify the same tokens without importing `console.backend` (forbidden by
ADR-0002) and without console.backend importing `brain` (wrong direction, brain has heavy optional
deps). Both processes must be started with the same `OPS_SECRET_KEY` env var for this to work.
"""

from __future__ import annotations

import os

import jwt

DEFAULT_SECRET_KEY = "dev-secret-change-me"


def get_secret_key() -> str:
    return os.environ.get("OPS_SECRET_KEY", DEFAULT_SECRET_KEY)


def decode_token(token: str, secret: str) -> int | None:
    """Return the user id encoded in a valid token, else None."""
    try:
        payload = jwt.decode(token, secret, algorithms=["HS256"])
    except jwt.PyJWTError:
        return None
    sub = payload.get("sub")
    return int(sub) if isinstance(sub, str) and sub.isdigit() else None
