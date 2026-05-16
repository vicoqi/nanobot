"""Auth API endpoints: register and login."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status

from nanobot.manager.auth import create_access_token, hash_password, verify_password
from nanobot.manager.database import Database
from nanobot.manager.models import LoginRequest, RegisterRequest, TokenResponse
from nanobot.manager.app import get_db

router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.post("/register", response_model=TokenResponse)
async def register(req: RegisterRequest, db: Database = Depends(get_db)):
    existing = await db.get_user_by_username(req.username)
    if existing:
        raise HTTPException(status_code=400, detail="Username already exists")
    user = await db.create_user(req.username, hash_password(req.password))
    token = create_access_token({"sub": str(user.id)}, _get_secret())
    return TokenResponse(token=token)


@router.post("/login", response_model=TokenResponse)
async def login(req: LoginRequest, db: Database = Depends(get_db)):
    user = await db.get_user_by_username(req.username)
    if not user or not verify_password(req.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Invalid credentials")
    token = create_access_token({"sub": str(user.id)}, _get_secret())
    return TokenResponse(token=token)


def _get_secret() -> str:
    from nanobot.manager.app import get_config
    return get_config().manager.secret_key
