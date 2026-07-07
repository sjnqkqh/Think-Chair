import os

os.environ["LANGCHAIN_TRACING_V2"] = "false"
os.environ["LANGSMITH_TRACING"] = "false"

import pytest
from fastapi.testclient import TestClient
from langchain_core.language_models.fake_chat_models import FakeListChatModel
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.database import Base, get_database_session
from app.graph import llm_registry
from main import app as fastapi_app

test_engine = create_engine(
    "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
)
TestSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)
Base.metadata.create_all(bind=test_engine)


@pytest.fixture
def db_session():
    db = TestSessionLocal()
    try:
        yield db
    finally:
        db.close()


@pytest.fixture(autouse=True)
def setup_dependency_overrides():
    def override_get_db():
        db = TestSessionLocal()
        try:
            yield db
        finally:
            db.close()

    fastapi_app.dependency_overrides[get_database_session] = override_get_db

    yield

    fastapi_app.dependency_overrides.clear()


@pytest.fixture
def client():
    return TestClient(fastapi_app)


@pytest.fixture
def fake_llm():
    llm = FakeListChatModel(responses=["테스트 응답입니다."])
    original = llm_registry._registry.get("default")
    llm_registry.register("default", llm)
    yield llm
    if original is not None:
        llm_registry.register("default", original)
