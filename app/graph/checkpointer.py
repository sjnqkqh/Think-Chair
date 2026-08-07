from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver


def is_sqlite_checkpoint_target(conn_string: str) -> bool:
    """테스트·로컬 파일 경로용 SQLite 대상인지 판별한다."""
    if conn_string == ":memory:" or conn_string.startswith("sqlite:"):
        return True
    # 확장자 .db 파일 경로 (구 기본값·테스트 호환)
    if "://" not in conn_string:
        return True
    return False


def normalize_checkpoint_conn_string(database_url: str) -> str:
    """SQLAlchemy URL을 AsyncPostgresSaver용 libpq URI로 맞춘다."""
    return database_url.replace("postgresql+psycopg://", "postgresql://", 1)


# AsyncSqliteSaver.from_conn_string() / AsyncPostgresSaver.from_conn_string()은
# async context manager를 반환한다. 호출부는 AsyncExitStack으로 연다.
def make_checkpointer(conn_string: str = ":memory:"):
    if is_sqlite_checkpoint_target(conn_string):
        return AsyncSqliteSaver.from_conn_string(conn_string)

    from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver

    return AsyncPostgresSaver.from_conn_string(
        normalize_checkpoint_conn_string(conn_string)
    )
