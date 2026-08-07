"""앱 기동·컷오버가 공유하는 스키마 DDL.

CREATE / IF NOT EXISTS 만 수행한다. 기존 테이블에 대한 ALTER 패치는 하지 않는다.
"""

from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.engine import Engine

import app.models  # noqa: F401
from app.core.database import Base, is_sqlite_url
from app.research.evidence_index import ensure_evidence_schema_ddl


def apply_runtime_ddl(database_url: str, engine: Engine) -> None:
    """런타임에 필요한 DDL을 실행한다.

    - Postgres: ``vector`` 확장
    - 앱 ORM 테이블 (``create_all``)
    - 근거 인덱스 계약·청크 테이블용 최소 DDL (확장·계약 테이블)
    """
    if not is_sqlite_url(database_url):
        with engine.begin() as conn:
            conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))

    Base.metadata.create_all(bind=engine)
    ensure_evidence_schema_ddl(database_url, engine)
