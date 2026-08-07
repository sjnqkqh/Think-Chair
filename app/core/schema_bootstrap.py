"""이전/초기화 스크립트용 스키마 생성.

앱 기동에서는 호출하지 않는다. 테이블 구조 변경(ALTER)도 여기서 하지 않는다.
"""

from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.engine import Engine

import app.models  # noqa: F401
from app.core.database import Base, is_sqlite_url
from app.research.evidence_index import ensure_evidence_schema_ddl


def create_app_schema(
    database_url: str,
    engine: Engine,
    *,
    embedding_model: str = "text-embedding-3-small",
    embedding_dimension: int = 1536,
    chunk_schema_version: str | None = None,
) -> None:
    """PostgreSQL/SQLite에 앱·근거 검색용 테이블을 만든다.

    - Postgres: ``vector`` 확장
    - 앱 ORM 테이블
    - 근거 계약·청크 테이블과 기본 계약 행
    """
    if chunk_schema_version is None:
        from app.research.source_chunking import CHUNK_SCHEMA_VERSION

        chunk_schema_version = CHUNK_SCHEMA_VERSION

    if not is_sqlite_url(database_url):
        with engine.begin() as conn:
            conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))

    Base.metadata.create_all(bind=engine)
    ensure_evidence_schema_ddl(
        database_url,
        engine,
        embedding_model=embedding_model,
        embedding_dimension=embedding_dimension,
        chunk_schema_version=chunk_schema_version,
    )
