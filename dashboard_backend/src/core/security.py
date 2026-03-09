from __future__ import annotations

import datetime as dt
from typing import Any, Dict, Optional

import jwt
from passlib.context import CryptContext

from src.core.config import get_settings

PWD_CONTEXT = CryptContext(schemes=["bcrypt"], deprecated="auto")


# PUBLIC_INTERFACE
def hash_password(password: str) -> str:
    """Hash a password using bcrypt."""
    return PWD_CONTEXT.hash(password)


# PUBLIC_INTERFACE
def verify_password(password: str, password_hash: str) -> bool:
    """Verify password against stored hash."""
    return PWD_CONTEXT.verify(password, password_hash)


# PUBLIC_INTERFACE
def create_access_token(
    *,
    subject: str,
    expires_minutes: Optional[int] = None,
    claims: Optional[Dict[str, Any]] = None,
) -> tuple[str, int]:
    """Create a signed JWT access token.

    Returns (token, expires_in_seconds).
    """
    settings = get_settings()
    exp_minutes = expires_minutes or settings.jwt_access_token_expire_minutes
    now = dt.datetime.utcnow()
    exp = now + dt.timedelta(minutes=exp_minutes)

    payload: Dict[str, Any] = {
        "sub": subject,
        "iat": int(now.timestamp()),
        "exp": int(exp.timestamp()),
    }
    if claims:
        payload.update(claims)

    token = jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)
    return token, int((exp - now).total_seconds())


# PUBLIC_INTERFACE
def decode_token(token: str) -> Dict[str, Any]:
    """Decode and validate a JWT token. Raises jwt exceptions on failure."""
    settings = get_settings()
    return jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
