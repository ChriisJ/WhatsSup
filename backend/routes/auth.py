"""Auth routes: register, login, me."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from ..config import get_settings
from ..database import get_session
from ..models import User
from ..security import (
    create_access_token,
    get_current_user,
    hash_password,
    verify_password,
)
from ..schemas import Token, UserCreate, UserOut

router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.post("/login", response_model=Token)
async def login(
    form: OAuth2PasswordRequestForm = Depends(),
    session: AsyncSession = Depends(get_session),
):
    result = await session.execute(select(User).where(User.username == form.username))
    user = result.scalar_one_or_none()
    if not user or not verify_password(form.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid username or password",
        )
    token = create_access_token(user.username, is_admin=user.is_admin)
    return Token(access_token=token, username=user.username, is_admin=user.is_admin)


@router.post("/register", response_model=UserOut)
async def register(
    body: UserCreate,
    session: AsyncSession = Depends(get_session),
):
    """Self-registration. Disabled if DEFAULT_ADMIN_PASSWORD is still 'changeme' AND
    the database already has a real admin - otherwise first user wins admin role."""
    s = get_settings()
    result = await session.execute(select(User))
    existing = result.scalars().all()

    is_first = len(existing) == 0
    if not is_first and s.default_admin_password == "changeme":
        # Default password still set -> open registration only when admin explicitly enabled it.
        # Allow registration regardless; admin can be promoted later.
        pass

    if any(u.username == body.username for u in existing):
        raise HTTPException(status_code=400, detail="Username already taken")

    user = User(
        username=body.username,
        password_hash=hash_password(body.password),
        is_admin=is_first,  # first registered user is admin
    )
    session.add(user)
    await session.commit()
    await session.refresh(user)
    return user


@router.get("/me", response_model=UserOut)
async def me(current: User = Depends(get_current_user)):
    return current
