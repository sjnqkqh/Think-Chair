"""checkpointer 연결 문자열·백엔드 선택 단위 테스트."""

from app.graph.checkpointer import (
    is_sqlite_checkpoint_target,
    normalize_checkpoint_conn_string,
)


def test_memory_and_sqlite_paths_use_sqlite_backend():
    assert is_sqlite_checkpoint_target(":memory:")
    assert is_sqlite_checkpoint_target("sqlite://")
    assert is_sqlite_checkpoint_target("/tmp/draftsmith_checkpoint.db")
    assert not is_sqlite_checkpoint_target(
        "postgresql://thinkchair:thinkchair@localhost:5432/thinkchair"
    )


def test_normalize_strips_sqlalchemy_psycopg_driver():
    assert (
        normalize_checkpoint_conn_string(
            "postgresql+psycopg://thinkchair:thinkchair@db:5432/thinkchair"
        )
        == "postgresql://thinkchair:thinkchair@db:5432/thinkchair"
    )
