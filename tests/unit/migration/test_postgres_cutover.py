"""Postgres 컷오버 마이그레이션 단위 테스트."""

import os
import uuid
from datetime import datetime

import pytest
from sqlalchemy.orm import sessionmaker

from app.core.database import Base, build_engine
from app.migration.postgres_cutover import (
    APP_TABLE_ORDER,
    TargetNotEmptyError,
    copy_app_tables,
    copy_checkpointer_sqlite_to_postgres,
    count_rows,
    format_report,
    migrate_sqlite_file_to_postgres,
)
from app.models.user import User

pytestmark = pytest.mark.unit

_PG_URL = os.environ.get(
    "TEST_POSTGRES_URL",
    "postgresql+psycopg://thinkchair:thinkchair@localhost:5432/thinkchair",
)


def _postgres_reachable(url: str) -> bool:
    try:
        engine = build_engine(url)
        with engine.connect() as conn:
            conn.exec_driver_sql("SELECT 1")
        engine.dispose()
        return True
    except Exception:
        return False


requires_postgres = pytest.mark.skipif(
    not _postgres_reachable(_PG_URL),
    reason="local Postgres unavailable",
)


def _seed_user(engine) -> uuid.UUID:
    SessionLocal = sessionmaker(bind=engine)
    user_id = uuid.uuid4()
    with SessionLocal() as session:
        session.add(
            User(
                id=user_id,
                login_id="migrate-user",
                password_hash="hash",
                nickname="migrator",
                created_at=datetime.utcnow(),
            )
        )
        session.commit()
    return user_id


def test_copy_app_tables_sqlite_to_sqlite(tmp_path):
    source_path = tmp_path / "source.db"
    target_path = tmp_path / "target.db"
    source_url = f"sqlite:///{source_path}"
    target_url = f"sqlite:///{target_path}"

    source = build_engine(source_url)
    target = build_engine(target_url)
    Base.metadata.create_all(bind=source)
    Base.metadata.create_all(bind=target)
    user_id = _seed_user(source)
    source.dispose()
    target.dispose()

    stats = copy_app_tables(source_url=source_url, target_url=target_url)
    users = next(item for item in stats if item.table == "users")
    assert users.source_count == 1
    assert users.copied == 1

    target = build_engine(target_url)
    assert count_rows(target, "users") == 1
    target.dispose()

    with pytest.raises(TargetNotEmptyError):
        copy_app_tables(source_url=source_url, target_url=target_url)

    again = copy_app_tables(
        source_url=source_url, target_url=target_url, replace_target=True
    )
    users_again = next(item for item in again if item.table == "users")
    assert users_again.copied == 1
    assert user_id  # seed 사용 확인


def test_dry_run_migrate_sqlite_file(tmp_path):
    source_path = tmp_path / "rag_history.db"
    source_url = f"sqlite:///{source_path}"
    source = build_engine(source_url)
    Base.metadata.create_all(bind=source)
    _seed_user(source)
    source.dispose()

    report = migrate_sqlite_file_to_postgres(
        sqlite_path=source_path,
        postgres_url="postgresql+psycopg://unused:unused@localhost:5432/unused",
        dry_run=True,
        setup_schema=True,
        skip_checkpoints=True,
    )
    assert report.schema_ok is False
    users = next(item for item in report.tables if item.table == "users")
    assert users.source_count == 1
    assert users.copied == 0
    assert "users" in APP_TABLE_ORDER
    assert "total_copied=0" in format_report(report)
    assert report.checkpoints is not None
    assert report.checkpoints.skipped is True


@requires_postgres
def test_copy_checkpointer_sqlite_to_postgres(tmp_path):
    import asyncio

    from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver

    from app.graph.checkpointer import make_checkpointer, normalize_checkpoint_conn_string
    from app.migration.postgres_cutover import ensure_postgres_schema

    src_path = tmp_path / "draftsmith_checkpoint.db"
    thread_id = f"migrate-cp-{uuid.uuid4()}"
    ensure_postgres_schema(_PG_URL)

    async def _seed() -> None:
        async with AsyncSqliteSaver.from_conn_string(str(src_path)) as src:
            await src.setup()
            parent = {"configurable": {"thread_id": thread_id, "checkpoint_ns": ""}}
            ckpt1 = {
                "v": 4,
                "ts": "2026-08-07T00:00:00+00:00",
                "id": "1f000000-0000-4000-8000-000000000001",
                "channel_values": {"messages": ["hello"], "topic": "t"},
                "channel_versions": {"messages": "1", "topic": "1"},
                "versions_seen": {},
            }
            await src.aput(
                parent, ckpt1, {"source": "input", "step": -1}, ckpt1["channel_versions"]
            )
            mid = {
                "configurable": {
                    "thread_id": thread_id,
                    "checkpoint_ns": "",
                    "checkpoint_id": ckpt1["id"],
                }
            }
            ckpt2 = {
                "v": 4,
                "ts": "2026-08-07T00:00:01+00:00",
                "id": "1f000000-0000-4000-8000-000000000002",
                "channel_values": {"messages": ["hello", "world"], "topic": "t"},
                "channel_versions": {"messages": "2", "topic": "1"},
                "versions_seen": {},
            }
            await src.aput(
                mid, ckpt2, {"source": "loop", "step": 0}, ckpt2["channel_versions"]
            )
            await src.aput_writes(
                {
                    "configurable": {
                        "thread_id": thread_id,
                        "checkpoint_ns": "",
                        "checkpoint_id": ckpt2["id"],
                    }
                },
                [("topic", "t")],
                task_id="task-1",
            )

    asyncio.run(_seed())

    dry = copy_checkpointer_sqlite_to_postgres(
        sqlite_path=src_path,
        postgres_url=_PG_URL,
        dry_run=True,
    )
    assert dry.threads == 1
    assert dry.checkpoints == 2

    stats = copy_checkpointer_sqlite_to_postgres(
        sqlite_path=src_path,
        postgres_url=_PG_URL,
        replace_target=False,
    )
    assert stats.checkpoints == 2
    assert stats.writes >= 1

    with pytest.raises(TargetNotEmptyError):
        copy_checkpointer_sqlite_to_postgres(
            sqlite_path=src_path,
            postgres_url=_PG_URL,
            replace_target=False,
        )

    async def _verify() -> None:
        async with make_checkpointer(normalize_checkpoint_conn_string(_PG_URL)) as dst:
            got = await dst.aget_tuple({"configurable": {"thread_id": thread_id}})
            assert got is not None
            assert got.checkpoint["id"] == "1f000000-0000-4000-8000-000000000002"
            assert got.checkpoint["channel_values"]["messages"] == ["hello", "world"]
            await dst.adelete_thread(thread_id)

    asyncio.run(_verify())
