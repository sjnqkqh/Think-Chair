import os
from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker
from app.core.config import settings

DATABASE_URL = f"sqlite:///{os.path.join(settings.BASE_DIR, 'rag_history.db')}"

engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


def get_database_session():
    database_session = SessionLocal()
    try:
        yield database_session
    finally:
        database_session.close()
