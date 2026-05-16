"""Authentication: password hashing, JWT tokens, and FastAPI dependencies."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
import bcrypt as _bcrypt
from jose import JWTError, jwt

ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_HOURS = 24

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login")


def hash_password(password: str) -> str:
    return _bcrypt.hashpw(password.encode(), _bcrypt.gensalt()).decode()


def verify_password(plain: str, hashed: str) -> bool:
    return _bcrypt.checkpw(plain.encode(), hashed.encode())


def create_access_token(data: dict, secret_key: str, expires_delta: timedelta | None = None) -> str:
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + (expires_delta or timedelta(hours=ACCESS_TOKEN_EXPIRE_HOURS))
    to_encode["exp"] = expire
    return jwt.encode(to_encode, secret_key, algorithm=ALGORITHM)


def decode_access_token(token: str, secret_key: str) -> dict | None:
    try:
        payload = jwt.decode(token, secret_key, algorithms=[ALGORITHM])
        return payload
    except JWTError:
        return None


def create_admin_token(admin_password: str, config_password: str, secret_key: str) -> str | None:
    if admin_password != config_password:
        return None
    return create_access_token({"role": "admin"}, secret_key)


# -- FastAPI dependencies --


async def get_current_user(
    token: str = Depends(oauth2_scheme),
) -> dict:
    """Validate JWT and return user payload. DB lookup is done in the route handler."""
    from nanobot.manager.app import get_config

    config = get_config()
    payload = decode_access_token(token, config.manager.secret_key)
    if payload is None or "sub" not in payload:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return payload


async def get_current_admin(
    token: str = Depends(oauth2_scheme),
) -> dict:
    """Validate JWT has admin role."""
    from nanobot.manager.app import get_config

    config = get_config()
    payload = decode_access_token(token, config.manager.secret_key)
    if payload is None or payload.get("role") != "admin":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Admin access required",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return payload
