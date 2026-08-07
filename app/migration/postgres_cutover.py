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
class CheckpointCopyStats:
    threads: int = 0
    checkpoints: int = 0
    writes: int = 0
    skipped: bool = False


@dataclass
class MigrationReport:
    schema_ok: bool = False
    tables: list[TableCopyStats] = field(default_factory=list)
    checkpoints: CheckpointCopyStats | None = None
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


class TargetNotEmptyError(RuntimeError):
    """대상 DB에 이미 앱 데이터가 있어 복사를 중단한다."""


def nonempty_app_tables(
    engine: Engine, tables: Sequence[str] = APP_TABLE_ORDER
) -> dict[str, int]:
    found: dict[str, int] = {}
    for table_name in tables:
        try:
            n = count_rows(engine, table_name)
        except Exception:
            continue
        if n > 0:
            found[table_name] = n
    return found


def truncate_app_tables(
    engine: Engine, tables: Sequence[str] = APP_TABLE_ORDER
) -> None:
    """FK 역순으로 앱 테이블 데이터를 비운다."""
    ordered = list(reversed(tuple(tables)))
    with engine.begin() as conn:
        if engine.dialect.name == "postgresql":
            from sqlalchemy import text

            joined = ", ".join(ordered)
            conn.execute(text(f"TRUNCATE {joined} RESTART IDENTITY CASCADE"))
            return
        from sqlalchemy import text

        for table_name in ordered:
            conn.execute(text(f"DELETE FROM {table_name}"))


def copy_app_tables(
    *,
    source_url: str,
    target_url: str,
    tables: Sequence[str] = APP_TABLE_ORDER,
    dry_run: bool = False,
    replace_target: bool = False,
) -> list[TableCopyStats]:
    """소스 DB 테이블 행을 타겟으로 복사한다. dry_run이면 소스 건수만 센다.

    대상에 이미 행이 있으면 기본은 중단한다. replace_target=True면 비운 뒤 복사한다.
    """
    source = create_engine(source_url)
    stats: list[TableCopyStats] = []
    target: Engine | None = None
    try:
        if not dry_run:
            target = build_engine(target_url)
            create_app_schema(target_url, target)
            existing = nonempty_app_tables(target, tables)
            if existing and not replace_target:
                detail = ", ".join(f"{name}={n}" for name, n in existing.items())
                raise TargetNotEmptyError(
                    "대상 DB에 이미 데이터가 있습니다. "
                    "잘못된 FK 복사를 막기 위해 중단했습니다. "
                    f"({detail}). "
                    "비우고 다시 넣으려면 --replace 를 사용하세요."
                )
            if existing and replace_target:
                truncate_app_tables(target, tables)

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
            if not rows:
                stats.append(
                    TableCopyStats(table=table_name, source_count=0, copied=0)
                )
                continue

            dst_meta = MetaData()
            dst_table = Table(table_name, dst_meta, autoload_with=target)
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


CHECKPOINTER_DATA_TABLES: tuple[str, ...] = (
    "checkpoint_writes",
    "checkpoint_blobs",
    "checkpoints",
)


def truncate_checkpointer_tables(postgres_url: str) -> None:
    """대화 그래프 데이터 테이블만 비운다 (migrations 메타는 유지)."""
    from sqlalchemy import text

    engine = build_engine(postgres_url)
    try:
        joined = ", ".join(CHECKPOINTER_DATA_TABLES)
        with engine.begin() as conn:
            conn.execute(text(f"TRUNCATE {joined} RESTART IDENTITY CASCADE"))
    finally:
        engine.dispose()


async def _list_checkpoint_thread_ids(source) -> list[str]:
    async with source.conn.execute(
        "SELECT DISTINCT thread_id FROM checkpoints ORDER BY thread_id"
    ) as cur:
        rows = await cur.fetchall()
    return [str(row[0]) for row in rows]


def _existing_checkpoint_thread_ids(postgres_url: str) -> set[str]:
    from sqlalchemy import text

    engine = build_engine(postgres_url)
    try:
        with engine.connect() as conn:
            rows = conn.execute(text("SELECT DISTINCT thread_id FROM checkpoints")).all()
            return {str(row[0]) for row in rows}
    except Exception:
        return set()
    finally:
        engine.dispose()


async def _copy_checkpointer_async(
    *,
    sqlite_path: Path,
    postgres_url: str,
    dry_run: bool = False,
    replace_target: bool = False,
) -> CheckpointCopyStats:
    """LangGraph SQLite 저장 → Postgres 저장 (스키마가 달라 API로 재기록)."""
    from collections import defaultdict

    from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver

    from app.graph.checkpointer import make_checkpointer, normalize_checkpoint_conn_string

    stats = CheckpointCopyStats()
    async with AsyncSqliteSaver.from_conn_string(str(sqlite_path.resolve())) as source:
        thread_ids = await _list_checkpoint_thread_ids(source)
        stats.threads = len(thread_ids)

        if dry_run:
            async with source.conn.execute("SELECT COUNT(*) FROM checkpoints") as cur:
                stats.checkpoints = int((await cur.fetchone())[0])
            async with source.conn.execute("SELECT COUNT(*) FROM writes") as cur:
                stats.writes = int((await cur.fetchone())[0])
            return stats

        if replace_target:
            truncate_checkpointer_tables(postgres_url)
        else:
            overlap = sorted(
                set(thread_ids) & _existing_checkpoint_thread_ids(postgres_url)
            )
            if overlap:
                sample = ", ".join(overlap[:5])
                more = f" 외 {len(overlap) - 5}개" if len(overlap) > 5 else ""
                raise TargetNotEmptyError(
                    "대상 Postgres에 같은 대화 스레드가 이미 있습니다. "
                    f"({sample}{more}). "
                    "비우고 다시 넣으려면 --replace 를 사용하세요."
                )

        async with make_checkpointer(
            normalize_checkpoint_conn_string(postgres_url)
        ) as target:
            setup = getattr(target, "setup", None)
            if setup is not None:
                await setup()

            for thread_id in thread_ids:
                tuples = [
                    item
                    async for item in source.alist(
                        {"configurable": {"thread_id": thread_id}}
                    )
                ]
                # alist는 최신→과거. 부모를 먼저 넣으려면 과거→최신.
                for item in reversed(tuples):
                    cfg = item.config["configurable"]
                    checkpoint_ns = cfg.get("checkpoint_ns", "")
                    parent = item.parent_config or {
                        "configurable": {
                            "thread_id": thread_id,
                            "checkpoint_ns": checkpoint_ns,
                        }
                    }
                    new_versions = item.checkpoint.get("channel_versions") or {}
                    await target.aput(
                        parent, item.checkpoint, item.metadata, new_versions
                    )
                    stats.checkpoints += 1

                    pending = item.pending_writes or []
                    by_task: dict[str, list[tuple[str, object]]] = defaultdict(list)
                    for task_id, channel, value in pending:
                        by_task[str(task_id)].append((channel, value))
                    write_config = {
                        "configurable": {
                            "thread_id": thread_id,
                            "checkpoint_ns": checkpoint_ns,
                            "checkpoint_id": item.checkpoint["id"],
                        }
                    }
                    for task_id, pairs in by_task.items():
                        await target.aput_writes(write_config, pairs, task_id)
                        stats.writes += len(pairs)

    return stats


def copy_checkpointer_sqlite_to_postgres(
    *,
    sqlite_path: Path,
    postgres_url: str,
    dry_run: bool = False,
    replace_target: bool = False,
) -> CheckpointCopyStats:
    """대화 이어가기 SQLite 파일 → Postgres 이전."""
    import asyncio

    if not sqlite_path.is_file():
        raise FileNotFoundError(f"checkpoint SQLite not found: {sqlite_path}")
    if is_sqlite_url(postgres_url):
        raise ValueError("checkpointer target must be Postgres")

    return asyncio.run(
        _copy_checkpointer_async(
            sqlite_path=sqlite_path,
            postgres_url=postgres_url,
            dry_run=dry_run,
            replace_target=replace_target,
        )
    )


def migrate_sqlite_file_to_postgres(
    *,
    sqlite_path: Path,
    postgres_url: str,
    dry_run: bool = False,
    setup_schema: bool = True,
    replace_target: bool = False,
    checkpoint_sqlite_path: Path | None = None,
    skip_checkpoints: bool = False,
    app_tables: bool = True,
) -> MigrationReport:
    """로컬 rag_history.db → Postgres 이전 진입점."""
    if app_tables and not sqlite_path.is_file():
        raise FileNotFoundError(f"SQLite DB not found: {sqlite_path}")

    report = MigrationReport()
    source_url = f"sqlite:///{sqlite_path.resolve()}" if sqlite_path.is_file() else ""

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

    if app_tables:
        if replace_target and not dry_run:
            report.notes.append("대상 앱 테이블을 비운 뒤 복사한다 (--replace)")

        report.tables = copy_app_tables(
            source_url=source_url,
            target_url=postgres_url,
            dry_run=dry_run,
            replace_target=replace_target,
        )
    else:
        report.notes.append("앱 테이블 복사를 건너뛴다 (--checkpoints-only)")

    if skip_checkpoints:
        report.checkpoints = CheckpointCopyStats(skipped=True)
        report.notes.append("대화 이어가기 이전을 건너뛴다 (--skip-checkpoints)")
    elif checkpoint_sqlite_path is None:
        report.checkpoints = CheckpointCopyStats(skipped=True)
        report.notes.append(
            "대화 이어가기 SQLite 경로가 없어 이전하지 않는다. "
            "--checkpoint-sqlite 로 지정할 수 있다."
        )
    elif not checkpoint_sqlite_path.is_file():
        report.checkpoints = CheckpointCopyStats(skipped=True)
        report.notes.append(
            f"대화 이어가기 SQLite 파일이 없어 건너뛴다: {checkpoint_sqlite_path}"
        )
    else:
        if replace_target and not dry_run:
            report.notes.append("대상 대화 그래프 저장을 비운 뒤 다시 넣는다 (--replace)")
        report.checkpoints = copy_checkpointer_sqlite_to_postgres(
            sqlite_path=checkpoint_sqlite_path,
            postgres_url=postgres_url,
            dry_run=dry_run,
            replace_target=replace_target,
        )
        report.notes.append(
            "대화 이어가기는 SQLite·Postgres 저장 형식이 달라 "
            "LangGraph API로 읽어 Postgres에 다시 기록한다."
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
    if report.checkpoints is not None:
        cp = report.checkpoints
        if cp.skipped:
            lines.append("checkpoints: skipped")
        else:
            lines.append(
                f"checkpoints: threads={cp.threads} "
                f"checkpoints={cp.checkpoints} writes={cp.writes}"
            )
    if report.notes:
        lines.append("notes:")
        for note in report.notes:
            lines.append(f"  - {note}")
    return "\n".join(lines)


