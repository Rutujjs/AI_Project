"""Security utilities for Member 5: Password hashing, verification and JWT tokens.

Provides:
- Secure password hashing (PBKDF2-HMAC-SHA256 with random salt & bcrypt interoperability)
- Standards-compliant JWT creation and decoding with HS256 signature
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import secrets
import time
from datetime import datetime, timedelta, timezone
from typing import Any

from app.platform.config import get_secret_key, ALGORITHM, ACCESS_TOKEN_EXPIRE_MINUTES


# ─── Password Hashing & Verification ───────────────────────────────────────────

def hash_password(password: str) -> str:
    """Hash a password securely using PBKDF2-HMAC-SHA256 with 100,000 rounds and a random salt.

    Falls back cleanly without native C-extension dependencies.
    """
    salt = secrets.token_hex(16)
    key = hashlib.pbkdf2_hmac(
        hash_name="sha256",
        password=password.encode("utf-8"),
        salt=salt.encode("utf-8"),
        iterations=100_000,
    )
    return f"pbkdf2:sha256:100000${salt}${key.hex()}"


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify that a plain password matches the stored hash.

    Supports both PBKDF2 hashes and standard bcrypt hashes.
    """
    if not plain_password or not hashed_password:
        return False

    # Check for PBKDF2 format
    if hashed_password.startswith("pbkdf2:sha256:"):
        parts = hashed_password.split("$")
        if len(parts) == 3:
            salt = parts[1]
            stored_key = parts[2]
            key = hashlib.pbkdf2_hmac(
                hash_name="sha256",
                password=plain_password.encode("utf-8"),
                salt=salt.encode("utf-8"),
                iterations=100_000,
            )
            return hmac.compare_digest(key.hex(), stored_key)

    # Check for bcrypt format ($2b$ or $2a$)
    if hashed_password.startswith(("$2b$", "$2a$")):
        try:
            import bcrypt
            return bcrypt.checkpw(plain_password.encode("utf-8"), hashed_password.encode("utf-8"))
        except Exception:
            pass

    return False


# ─── JWT Creation & Decoding (HS256) ───────────────────────────────────────────

def _base64url_encode(data: bytes) -> str:
    """Encode bytes to base64url string without padding."""
    return base64.urlsafe_b64encode(data).decode("utf-8").rstrip("=")


def _base64url_decode(data: str) -> bytes:
    """Decode base64url string with padding restoration."""
    rem = len(data) % 4
    if rem > 0:
        data += "=" * (4 - rem)
    return base64.urlsafe_b64decode(data.encode("utf-8"))


def create_access_token(
    data: dict[str, Any],
    expires_delta: timedelta | None = None,
) -> str:
    """Create a signed JWT access token using HMAC-SHA256."""
    to_encode = data.copy()
    now = datetime.now(timezone.utc)
    if expires_delta:
        expire = now + expires_delta
    else:
        expire = now + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)

    to_encode.setdefault("jti", secrets.token_hex(16))
    to_encode.update({
        "iat": int(now.timestamp()),
        "exp": int(expire.timestamp()),
    })

    header = {"alg": ALGORITHM, "typ": "JWT"}
    encoded_header = _base64url_encode(json.dumps(header, separators=(",", ":")).encode("utf-8"))
    encoded_payload = _base64url_encode(json.dumps(to_encode, separators=(",", ":")).encode("utf-8"))

    signing_input = f"{encoded_header}.{encoded_payload}".encode("utf-8")
    signature = hmac.new(
        key=get_secret_key().encode("utf-8"),
        msg=signing_input,
        digestmod=hashlib.sha256,
    ).digest()
    encoded_signature = _base64url_encode(signature)

    return f"{encoded_header}.{encoded_payload}.{encoded_signature}"


def decode_access_token(token: str) -> dict[str, Any]:
    """Decode and verify a signed JWT access token.

    Raises:
        ValueError if the token format, signature, or expiry is invalid.
    """
    try:
        parts = token.strip().split(".")
        if len(parts) != 3:
            raise ValueError("Token must contain exactly 3 segments")

        header_b64, payload_b64, signature_b64 = parts

        # Verify signature
        signing_input = f"{header_b64}.{payload_b64}".encode("utf-8")
        expected_sig = hmac.new(
            key=get_secret_key().encode("utf-8"),
            msg=signing_input,
            digestmod=hashlib.sha256,
        ).digest()
        provided_sig = _base64url_decode(signature_b64)

        if not hmac.compare_digest(expected_sig, provided_sig):
            raise ValueError("Invalid token signature")

        # Parse payload
        payload_bytes = _base64url_decode(payload_b64)
        payload = json.loads(payload_bytes.decode("utf-8"))

        # Verify expiry
        exp = payload.get("exp")
        if exp is not None:
            now_ts = int(time.time())
            if now_ts > int(exp):
                raise ValueError("Token has expired")

        return payload

    except ValueError:
        raise
    except Exception as exc:
        raise ValueError(f"Failed to decode token: {exc}")

