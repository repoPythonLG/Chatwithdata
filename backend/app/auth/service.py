from __future__ import annotations

import base64
import hashlib
import hmac
import logging
import secrets
from datetime import datetime, timedelta, timezone

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings, get_settings
from app.db.models import User, UserSession
from app.schemas.auth import UserCreate, UserUpdate

logger = logging.getLogger(__name__)

AUTH_COOKIE_NAME = "chat_with_contracts_session"
PASSWORD_HASH_ALGORITHM = "pbkdf2_sha256"
PASSWORD_HASH_ITERATIONS = 260_000


class AuthError(ValueError):
    """Raised for authentication failures."""


class AuthorizationError(PermissionError):
    """Raised for role or account-state failures."""


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt,
        PASSWORD_HASH_ITERATIONS,
    )
    return "$".join(
        [
            PASSWORD_HASH_ALGORITHM,
            str(PASSWORD_HASH_ITERATIONS),
            base64.urlsafe_b64encode(salt).decode("ascii"),
            base64.urlsafe_b64encode(digest).decode("ascii"),
        ]
    )


def verify_password(password: str, stored_hash: str) -> bool:
    try:
        algorithm, iterations, encoded_salt, encoded_digest = stored_hash.split("$", 3)
        if algorithm != PASSWORD_HASH_ALGORITHM:
            return False
        salt = base64.urlsafe_b64decode(encoded_salt.encode("ascii"))
        expected = base64.urlsafe_b64decode(encoded_digest.encode("ascii"))
        actual = hashlib.pbkdf2_hmac(
            "sha256",
            password.encode("utf-8"),
            salt,
            int(iterations),
        )
        return hmac.compare_digest(actual, expected)
    except Exception:
        return False


def hash_session_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


class AuthService:
    def __init__(self, session: AsyncSession, settings: Settings | None = None):
        self.session = session
        self.settings = settings or get_settings()

    async def authenticate(
        self,
        *,
        username: str,
        password: str,
        user_agent: str | None = None,
        ip_address: str | None = None,
    ) -> tuple[User, str, datetime]:
        user = await self.get_user_by_username(username)
        if user is None or not verify_password(password, user.password_hash):
            raise AuthError("Invalid username or password.")
        if not user.is_active:
            raise AuthError("This account is disabled.")

        raw_token = secrets.token_urlsafe(48)
        expires_at = utc_now() + timedelta(hours=self.settings.auth_session_hours)
        self.session.add(
            UserSession(
                user_id=user.id,
                token_hash=hash_session_token(raw_token),
                expires_at=expires_at,
                user_agent=(user_agent or "")[:1000] or None,
                ip_address=(ip_address or "")[:64] or None,
            )
        )
        user.last_login_at = utc_now()
        await self.session.commit()
        await self.session.refresh(user)
        return user, raw_token, expires_at

    async def user_from_token(self, token: str | None) -> User | None:
        if not token:
            return None
        statement = (
            select(UserSession, User)
            .join(User, User.id == UserSession.user_id)
            .where(UserSession.token_hash == hash_session_token(token))
            .where(UserSession.expires_at > utc_now())
            .where(User.is_active.is_(True))
        )
        result = await self.session.execute(statement)
        row = result.one_or_none()
        if row is None:
            return None
        return row[1]

    async def logout(self, token: str | None) -> None:
        if not token:
            return
        await self.session.execute(
            delete(UserSession).where(UserSession.token_hash == hash_session_token(token))
        )
        await self.session.commit()

    async def prune_expired_sessions(self) -> None:
        await self.session.execute(delete(UserSession).where(UserSession.expires_at <= utc_now()))
        await self.session.commit()

    async def list_users(self) -> list[User]:
        result = await self.session.execute(select(User).order_by(User.username))
        return list(result.scalars().all())

    async def get_user(self, user_id: str) -> User | None:
        return await self.session.get(User, user_id)

    async def get_user_by_username(self, username: str) -> User | None:
        result = await self.session.execute(
            select(User).where(func.lower(User.username) == username.strip().lower())
        )
        return result.scalars().one_or_none()

    async def create_user(self, payload: UserCreate) -> User:
        username = payload.username.strip()
        if await self.get_user_by_username(username):
            raise ValueError("A user with this username already exists.")

        user = User(
            username=username,
            display_name=payload.display_name.strip() if payload.display_name else username,
            role=payload.role,
            password_hash=hash_password(payload.password),
            is_active=payload.is_active,
        )
        self.session.add(user)
        await self.session.commit()
        await self.session.refresh(user)
        return user

    async def update_user(self, user_id: str, payload: UserUpdate) -> User:
        user = await self.get_user(user_id)
        if user is None:
            raise ValueError("User not found.")
        if payload.display_name is not None:
            user.display_name = payload.display_name.strip() or user.username
        if payload.role is not None:
            user.role = payload.role
        if payload.is_active is not None:
            user.is_active = payload.is_active
            if not payload.is_active:
                await self.session.execute(
                    delete(UserSession).where(UserSession.user_id == user.id)
                )
        await self.session.commit()
        await self.session.refresh(user)
        return user

    async def update_password(self, user_id: str, password: str) -> User:
        user = await self.get_user(user_id)
        if user is None:
            raise ValueError("User not found.")
        user.password_hash = hash_password(password)
        await self.session.execute(delete(UserSession).where(UserSession.user_id == user.id))
        await self.session.commit()
        await self.session.refresh(user)
        return user

    async def deactivate_user(self, user_id: str, acting_user: User) -> None:
        if user_id == acting_user.id:
            raise ValueError("Administrators cannot deactivate their own account.")
        user = await self.get_user(user_id)
        if user is None:
            return
        user.is_active = False
        await self.session.execute(delete(UserSession).where(UserSession.user_id == user.id))
        await self.session.commit()


async def ensure_default_admin(session: AsyncSession, settings: Settings | None = None) -> None:
    settings = settings or get_settings()
    result = await session.execute(select(func.count(User.id)))
    user_count = int(result.scalar_one())
    if user_count:
        return

    admin = User(
        username=settings.initial_admin_username,
        display_name="Administrator",
        role="admin",
        password_hash=hash_password(settings.initial_admin_password),
        is_active=True,
    )
    session.add(admin)
    await session.commit()
    logger.warning(
        "Created initial administrator account '%s'. Change the default password immediately.",
        settings.initial_admin_username,
    )
