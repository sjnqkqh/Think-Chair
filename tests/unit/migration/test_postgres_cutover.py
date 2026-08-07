"""Postgres 컷오버 마이그레이션 단위 테스트."""

import uuid
from datetime import datetime

import pytest
from sqlalchemy.orm import sessionmaker

from app.core.database import Base, build_engine
from app.migration.postgres_cutover import (
    APP_TABLE_ORDER,
    TargetNotEmptyError,
    copy_app_tables,
    count_rows,
    format_report,
    migrate_sqlite_file_to_postgres,
)
from app.models.user import User


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
    )
    assert report.schema_ok is False
    users = next(item for item in report.tables if item.table == "users")
    assert users.source_count == 1
    assert users.copied == 0
    assert "users" in APP_TABLE_ORDER
    assert "total_copied=0" in format_report(report)
