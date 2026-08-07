from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import declarative_base, sessionmaker

from app.core.config import settings


def is_sqlite_url(database_url: str) -> bool:
    return database_url.startswith("sqlite:")


def build_engine(database_url: str) -> Engine:
    if is_sqlite_url(database_url):
        engine = create_engine(
            database_url,
            connect_args={"check_same_thread": False, "timeout": 10},
        )

        @event.listens_for(engine, "connect")
        def _set_sqlite_pragma(dbapi_connection, connection_record):
            cursor = dbapi_connection.cursor()
            cursor.execute("PRAGMA journal_mode=WAL")
            cursor.execute("PRAGMA busy_timeout=10000")
            cursor.close()

        return engine

    return create_engine(database_url)


DATABASE_URL = settings.DATABASE_URL
engine = build_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


def get_database_session():
    database_session = SessionLocal()
    try:
        yield database_session
    finally:
        database_session.close()
