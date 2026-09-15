"""Password hashing + JWT helpers."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
from passlib.context import CryptContext
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from .config import get_settings
from .database import get_session
from .models import User

_pwd = CryptContext(schemes=["bcrypt"], deprecated="auto")
_oauth2 = OAuth2PasswordBearer(tokenUrl="/api/auth/login")


def hash_password(plain: str) -> str:
    return _pwd.hash(plain)


def verify_password(plain: str, hashed: str) -> bool:
    try:
        return _pwd.verify(plain, hashed)
    except Exception:
        return False


def create_access_token(subject: str, *, is_admin: bool) -> str:
    s = get_settings()
    expires = datetime.now(timezone.utc) + timedelta(days=7)
    payload = {
        "sub": subject,
        "is_admin": is_admin,
        "exp": expires,
    }
    return jwt.encode(payload, s.secret_key, algorithm="HS256")


def decode_token(token: str) -> Optional[dict]:
    s = get_settings()
    try:
        return jwt.decode(token, s.secret_key, algorithms=["HS256"])
    except JWTError:
        return None


async def get_current_user(
    token: str = Depends(_oauth2),
    session: AsyncSession = Depends(get_session),
) -> User:
    payload = decode_token(token)
    if not payload:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        )
    username = payload.get("sub")
    if not username:
        raise HTTPException(status_code=401, detail="Invalid token payload")

    result = await session.execute(select(User).where(User.username == username))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=401, detail="User not found")
    return user
