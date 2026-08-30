"""Password hashing (stdlib scrypt) and stateless per-user tokens (JWT).

No third-party hasher — `hashlib.scrypt` is a memory-hard KDF in the standard library, so the
dependency surface stays small and fully typed.
"""

from __future__ import annotations

import hashlib
import hmac
import secrets
import time

import jwt

_SCRYPT_N = 2**14
_SCRYPT_R = 8
_SCRYPT_P = 1
_DKLEN = 32
_TOKEN_TTL_S = 60 * 60 * 8  # 8 hours


def _scrypt(password: str, salt: bytes) -> bytes:
    return hashlib.scrypt(
        password.encode(), salt=salt, n=_SCRYPT_N, r=_SCRYPT_R, p=_SCRYPT_P, dklen=_DKLEN
    )


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    return f"scrypt${salt.hex()}${_scrypt(password, salt).hex()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        algo, salt_hex, hash_hex = stored.split("$")
    except ValueError:
        return False
    if algo != "scrypt":
        return False
    computed = _scrypt(password, bytes.fromhex(salt_hex)).hex()
    return hmac.compare_digest(computed, hash_hex)


def create_token(user_id: int, secret: str) -> str:
    payload = {"sub": str(user_id), "exp": int(time.time()) + _TOKEN_TTL_S}
    return jwt.encode(payload, secret, algorithm="HS256")


def decode_token(token: str, secret: str) -> int | None:
    """Return the user id encoded in a valid token, else None."""
    try:
        payload = jwt.decode(token, secret, algorithms=["HS256"])
    except jwt.PyJWTError:
        return None
    sub = payload.get("sub")
    return int(sub) if isinstance(sub, str) and sub.isdigit() else None
