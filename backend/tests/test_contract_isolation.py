from __future__ import annotations

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.agent.qwen_cli_engine import CONTRACT_DB_ROLE, QwenCliEngine
from app.db.models import Base, ContractDocument, DataSource, User


@pytest.mark.asyncio
async def test_qwen_engine_loads_only_current_user_documents_and_shared_contract_db():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", future=True)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with session_factory() as session:
        session.add_all(
            [
                User(
                    id="user-a",
                    username="user-a",
                    display_name="User A",
                    role="standard",
                    password_hash="x",
                ),
                User(
                    id="user-b",
                    username="user-b",
                    display_name="User B",
                    role="standard",
                    password_hash="x",
                ),
                DataSource(
                    id="shared-db",
                    name="Contract database",
                    source_type="sqlite",
                    path="/tmp/contracts.sqlite",
                    status="active",
                    profile={"role": CONTRACT_DB_ROLE},
                ),
                DataSource(
                    id="other-db",
                    name="Other database",
                    source_type="sqlite",
                    path="/tmp/other.sqlite",
                    status="active",
                    profile={},
                ),
                ContractDocument(
                    id="doc-a",
                    user_id="user-a",
                    name="A contract",
                    filename="a.txt",
                    path="/tmp/a.txt",
                    size_bytes=1,
                ),
                ContractDocument(
                    id="doc-b",
                    user_id="user-b",
                    name="B contract",
                    filename="b.txt",
                    path="/tmp/b.txt",
                    size_bytes=1,
                ),
            ]
        )
        await session.commit()

        user_a_engine = QwenCliEngine(session, user_id="user-a")
        user_a_docs = await user_a_engine._load_contract_documents()
        user_a_sources = await user_a_engine._load_sources(selected_data_sources=None)

        user_b_engine = QwenCliEngine(session, user_id="user-b")
        user_b_docs = await user_b_engine._load_contract_documents()

    await engine.dispose()

    assert [document.id for document in user_a_docs] == ["doc-a"]
    assert [document.id for document in user_b_docs] == ["doc-b"]
    assert [source.id for source in user_a_sources] == ["shared-db"]
