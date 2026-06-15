from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import admin_user, current_user
from app.auth.service import AUTH_COOKIE_NAME, AuthError, AuthService
from app.core.config import get_settings
from app.db.models import User
from app.db.session import get_session
from app.schemas.auth import LoginRequest, PasswordUpdate, UserCreate, UserOut, UserUpdate

auth_router = APIRouter(prefix="/auth", tags=["auth"])
users_router = APIRouter(prefix="/users", tags=["users"])


@auth_router.post("/login", response_model=UserOut)
async def login(
    payload: LoginRequest,
    request: Request,
    response: Response,
    session: AsyncSession = Depends(get_session),
):
    try:
        user, token, _expires_at = await AuthService(session).authenticate(
            username=payload.username,
            password=payload.password,
            user_agent=request.headers.get("user-agent"),
            ip_address=request.client.host if request.client else None,
        )
    except AuthError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(exc)) from exc

    settings = get_settings()
    response.set_cookie(
        AUTH_COOKIE_NAME,
        token,
        httponly=True,
        secure=settings.auth_cookie_secure,
        samesite="lax",
        max_age=settings.auth_session_hours * 60 * 60,
        path="/",
    )
    return user


@auth_router.post("/logout", status_code=204)
async def logout(
    request: Request,
    response: Response,
    session: AsyncSession = Depends(get_session),
):
    await AuthService(session).logout(request.cookies.get(AUTH_COOKIE_NAME))
    response.delete_cookie(AUTH_COOKIE_NAME, path="/")


@auth_router.get("/me", response_model=UserOut)
async def me(user: User = Depends(current_user)):
    return user


@users_router.get("", response_model=list[UserOut])
async def list_users(
    _admin: User = Depends(admin_user),
    session: AsyncSession = Depends(get_session),
):
    return await AuthService(session).list_users()


@users_router.post("", response_model=UserOut)
async def create_user(
    payload: UserCreate,
    _admin: User = Depends(admin_user),
    session: AsyncSession = Depends(get_session),
):
    try:
        return await AuthService(session).create_user(payload)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@users_router.patch("/{user_id}", response_model=UserOut)
async def update_user(
    user_id: str,
    payload: UserUpdate,
    _admin: User = Depends(admin_user),
    session: AsyncSession = Depends(get_session),
):
    try:
        return await AuthService(session).update_user(user_id, payload)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@users_router.post("/{user_id}/password", response_model=UserOut)
async def update_user_password(
    user_id: str,
    payload: PasswordUpdate,
    _admin: User = Depends(admin_user),
    session: AsyncSession = Depends(get_session),
):
    try:
        return await AuthService(session).update_password(user_id, payload.password)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@users_router.delete("/{user_id}", status_code=204)
async def deactivate_user(
    user_id: str,
    acting_user: User = Depends(admin_user),
    session: AsyncSession = Depends(get_session),
):
    try:
        await AuthService(session).deactivate_user(user_id, acting_user)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
