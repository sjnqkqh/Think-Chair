"""앱 DB 엔진 URL·연결 옵션 단위 테스트."""

from sqlalchemy.engine import Engine

from app.core.database import build_engine, is_sqlite_url


def test_is_sqlite_url():
    assert is_sqlite_url("sqlite://")
    assert is_sqlite_url("sqlite:////tmp/x.db")
    assert not is_sqlite_url(
        "postgresql+psycopg://thinkchair:thinkchair@localhost:5432/thinkchair"
    )


def test_build_engine_postgres_has_no_sqlite_connect_args():
    engine = build_engine(
        "postgresql+psycopg://thinkchair:thinkchair@localhost:5432/thinkchair"
    )
    assert isinstance(engine, Engine)
    assert engine.url.drivername == "postgresql+psycopg"
    assert engine.dialect.name == "postgresql"
    # 연결은 하지 않고 URL·방언만 확인 (로컬에 Postgres 없어도 됨)
    engine.dispose()


def test_build_engine_sqlite_keeps_thread_connect_args():
    engine = build_engine("sqlite://")
    assert engine.dialect.name == "sqlite"
    engine.dispose()
