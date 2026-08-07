"""SQLite 앱 DB → Postgres 스키마·데이터 이전.

스키마 생성은 ``create_app_schema`` + 대화 그래프 저장 테이블 준비로만 한다.
앱 기동에서는 테이블을 만들지 않는다. 컬럼 패치용 ALTER도 하지 않는다.
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path

from sqlalchemy import MetaData, Table, create_engine, func, select
from sqlalchemy.engine import Engine

import app.models  # noqa: F401 — Base.metadata 등록
from app.core.database import build_engine, is_sqlite_url
from app.core.schema_bootstrap import create_app_schema

# FK를 깨지 않는 복사 순서
APP_TABLE_ORDER: tuple[str, ...] = (
    "users",
    "manuscripts",
    "manuscript_versions",
    "manuscript_llm_settings",
    "document_evaluations",
    "chat_messages",
    "routing_decisions",
    "research_sources",
    "research_source_urls",
    "research_jobs",
    "research_job_sources",
    "research_usage",
)


@dataclass
class TableCopyStats:
    table: str
    source_count: int
    copied: int
    skipped_existing: int = 0


@dataclass
class MigrationReport:
    schema_ok: bool = False
    tables: list[TableCopyStats] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    @property
    def total_copied(self) -> int:
        return sum(item.copied for item in self.tables)


def ensure_postgres_schema(database_url: str) -> None:
    """이전 스크립트용: 앱·근거 테이블과 대화 그래프 저장 테이블을 만든다."""
    if is_sqlite_url(database_url):
        raise ValueError("ensure_postgres_schema requires a Postgres DATABASE_URL")

    engine = build_engine(database_url)
    try:
        create_app_schema(database_url, engine)
    finally:
        engine.dispose()

    _ensure_checkpointer_tables(database_url)


def _ensure_checkpointer_tables(database_url: str) -> None:
    """LangGraph AsyncPostgresSaver 테이블을 생성한다."""
    import asyncio

    from app.graph.checkpointer import (
        make_checkpointer,
        normalize_checkpoint_conn_string,
    )

    async def _setup() -> None:
        async with make_checkpointer(
            normalize_checkpoint_conn_string(database_url)
        ) as checkpointer:
            setup = getattr(checkpointer, "setup", None)
            if setup is not None:
                await setup()

    asyncio.run(_setup())


def _normalize_cell(value: object, *, as_uuid: bool) -> object:
    if as_uuid and isinstance(value, str):
        try:
            return uuid.UUID(value)
        except ValueError:
            return value
    if not as_uuid and isinstance(value, uuid.UUID):
        return str(value)
    return value


def _normalize_row(row: dict, *, as_uuid: bool) -> dict:
    return {
        key: _normalize_cell(value, as_uuid=as_uuid) for key, value in row.items()
    }


def count_rows(engine: Engine, table_name: str) -> int:
    metadata = MetaData()
    table = Table(table_name, metadata, autoload_with=engine)
    with engine.connect() as conn:
        return int(conn.execute(select(func.count()).select_from(table)).scalar_one())


def copy_app_tables(
    *,
    source_url: str,
    target_url: str,
    tables: Sequence[str] = APP_TABLE_ORDER,
    dry_run: bool = False,
    skip_if_target_nonempty: bool = True,
) -> list[TableCopyStats]:
    """소스 DB 테이블 행을 타겟으로 복사한다. dry_run이면 소스 건수만 센다."""
    source = create_engine(source_url)
    stats: list[TableCopyStats] = []
    target: Engine | None = None
    try:
        if not dry_run:
            target = build_engine(target_url)
            create_app_schema(target_url, target)

        target_wants_uuid = target is not None and not is_sqlite_url(target_url)

        for table_name in tables:
            src_meta = MetaData()
            src_table = Table(table_name, src_meta, autoload_with=source)
            with source.connect() as src_conn:
                rows = [
                    _normalize_row(dict(row), as_uuid=target_wants_uuid)
                    for row in src_conn.execute(select(src_table)).mappings().all()
                ]
            source_count = len(rows)

            if dry_run:
                stats.append(
                    TableCopyStats(
                        table=table_name, source_count=source_count, copied=0
                    )
                )
                continue

            assert target is not None
            dst_meta = MetaData()
            dst_table = Table(table_name, dst_meta, autoload_with=target)
            existing = count_rows(target, table_name)
            if skip_if_target_nonempty and existing > 0:
                stats.append(
                    TableCopyStats(
                        table=table_name,
                        source_count=source_count,
                        copied=0,
                        skipped_existing=existing,
                    )
                )
                continue

            if not rows:
                stats.append(
                    TableCopyStats(table=table_name, source_count=0, copied=0)
                )
                continue

            with target.begin() as dst_conn:
                dst_conn.execute(dst_table.insert(), rows)
            stats.append(
                TableCopyStats(
                    table=table_name, source_count=source_count, copied=len(rows)
                )
            )
    finally:
        source.dispose()
        if target is not None:
            target.dispose()
    return stats


def list_indexed_source_ids(database_url: str) -> list[uuid.UUID]:
    """재인덱싱 대상(INDEXED research_sources) id 목록."""
    from app.models.research import ResearchSource, ResearchSourceStatus

    engine = build_engine(database_url)
    try:
        with engine.connect() as conn:
            rows = conn.execute(
                select(ResearchSource.id).where(
                    ResearchSource.status == ResearchSourceStatus.INDEXED
                )
            ).all()
            return [row[0] for row in rows]
    finally:
        engine.dispose()


def migrate_sqlite_file_to_postgres(
    *,
    sqlite_path: Path,
    postgres_url: str,
    dry_run: bool = False,
    setup_schema: bool = True,
) -> MigrationReport:
    """로컬 rag_history.db → Postgres 이전 진입점."""
    if not sqlite_path.is_file():
        raise FileNotFoundError(f"SQLite DB not found: {sqlite_path}")

    report = MigrationReport()
    source_url = f"sqlite:///{sqlite_path.resolve()}"

    if setup_schema and not dry_run:
        ensure_postgres_schema(postgres_url)
        report.schema_ok = True
        report.notes.append(
            "스키마는 이전 스크립트의 create_app_schema + 대화 그래프 저장 테이블 준비로 만든다. "
            "앱 기동에서는 테이블을 만들지 않는다."
        )
    elif dry_run:
        report.notes.append("dry-run: schema setup skipped")
    else:
        report.schema_ok = True
        report.notes.append("schema setup skipped by flag")

    report.tables = copy_app_tables(
        source_url=source_url,
        target_url=postgres_url,
        dry_run=dry_run,
    )

    report.notes.append(
        "대화 이어가기(checkpointer) SQLite 파일은 이전하지 않는다. "
        "Postgres checkpointer는 빈 상태로 두고, 채팅 화면 이력은 앱 DB 행을 따른다."
    )
    report.notes.append(
        "근거 벡터(Chroma)는 덤프 이전하지 않는다. "
        "INDEXED research_sources는 원문 저장소를 기준으로 재인덱싱한다 "
        "(scripts/migrate_sqlite_to_postgres.py --list-reindex-targets)."
    )
    return report


def format_report(report: MigrationReport) -> str:
    lines = [
        f"schema_ok={report.schema_ok}",
        f"total_copied={report.total_copied}",
        "tables:",
    ]
    for item in report.tables:
        lines.append(
            f"  - {item.table}: source={item.source_count} "
            f"copied={item.copied} skipped_existing={item.skipped_existing}"
        )
    if report.notes:
        lines.append("notes:")
        for note in report.notes:
            lines.append(f"  - {note}")
    return "\n".join(lines)


