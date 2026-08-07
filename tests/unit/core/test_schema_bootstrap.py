"""스키마 생성(이전/초기화 스크립트용) 단위 테스트."""

from sqlalchemy import inspect, text

from app.core.database import build_engine
from app.core.schema_bootstrap import create_app_schema


def test_create_app_schema_makes_orm_and_evidence_tables(tmp_path):
    url = f"sqlite:///{tmp_path / 'boot.db'}"
    engine = build_engine(url)
    create_app_schema(
        url,
        engine,
        embedding_model="test-model",
        embedding_dimension=3,
        chunk_schema_version="test-schema",
    )

    inspector = inspect(engine)
    assert "users" in inspector.get_table_names()
    assert "manuscripts" in inspector.get_table_names()
    assert "evidence_chunks__research_public_v1" in inspector.get_table_names()
    with engine.connect() as conn:
        row = conn.execute(
            text(
                "SELECT embedding_model FROM evidence_index_contracts "
                "WHERE collection_name = 'research_public_v1'"
            )
        ).scalar_one()
    assert row == "test-model"
    engine.dispose()
