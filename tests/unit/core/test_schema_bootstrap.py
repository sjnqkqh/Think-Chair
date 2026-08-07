"""런타임 스키마 DDL 단위 테스트."""

from sqlalchemy import inspect, text

from app.core.database import build_engine
from app.core.schema_bootstrap import apply_runtime_ddl


def test_apply_runtime_ddl_creates_orm_and_evidence_contract(tmp_path):
    url = f"sqlite:///{tmp_path / 'boot.db'}"
    engine = build_engine(url)
    apply_runtime_ddl(url, engine)

    inspector = inspect(engine)
    assert "users" in inspector.get_table_names()
    assert "manuscripts" in inspector.get_table_names()
    with engine.connect() as conn:
        row = conn.execute(
            text(
                "SELECT name FROM sqlite_master "
                "WHERE type='table' AND name='evidence_index_contracts'"
            )
        ).scalar_one()
    assert row == "evidence_index_contracts"
    engine.dispose()
