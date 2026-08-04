"""테스트 DB에 ORM 테이블을 준비한다."""

import app.models  # noqa: F401

from app.core.database import Base
from app.research.schema_ensure import ensure_research_schema


def prepare_test_database(engine) -> None:
    """모든 ORM 모델을 등록한 뒤 테이블과 research 스키마 보정을 적용한다."""
    Base.metadata.create_all(bind=engine)
    ensure_research_schema(engine)
