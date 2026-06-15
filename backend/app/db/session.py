from __future__ import annotations

from collections.abc import AsyncIterator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import get_settings
from app.db.models import Base

settings = get_settings()
database_url = f"sqlite+aiosqlite:///{settings.metadata_db_path}"

engine = create_async_engine(database_url, future=True, echo=False)
AsyncSessionLocal = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)


async def init_db() -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        await _run_lightweight_migrations(conn)

    from app.auth.service import ensure_default_admin

    async with AsyncSessionLocal() as session:
        await ensure_default_admin(session)


async def _run_lightweight_migrations(conn) -> None:
    """Apply additive SQLite migrations for local metadata databases.

    The project intentionally avoids a heavyweight migration dependency for this
    single-file local metadata store. These migrations are additive and safe to
    run repeatedly.
    """

    await _add_column_if_missing(conn, "conversations", "user_id", "VARCHAR(36)")
    await _add_column_if_missing(conn, "contract_documents", "user_id", "VARCHAR(36)")
    await conn.exec_driver_sql(
        "CREATE INDEX IF NOT EXISTS ix_conversations_user_id ON conversations(user_id)"
    )
    await conn.exec_driver_sql(
        "CREATE INDEX IF NOT EXISTS ix_contract_documents_user_id ON contract_documents(user_id)"
    )


async def _add_column_if_missing(conn, table_name: str, column_name: str, definition: str) -> None:
    rows = await conn.exec_driver_sql(f"PRAGMA table_info({table_name})")
    existing = {row[1] for row in rows}
    if column_name not in existing:
        await conn.exec_driver_sql(
            f"ALTER TABLE {table_name} ADD COLUMN {column_name} {definition}"
        )


async def get_session() -> AsyncIterator[AsyncSession]:
    async with AsyncSessionLocal() as session:
        yield session
