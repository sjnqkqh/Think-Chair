from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.endpoints.evaluation import get_evaluator_service
from app.api.endpoints.query import get_rag_service
from app.core.database import Base, get_database_session
from app.services.evaluator import EvaluatorService
from app.services.rag import RagService
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
def setup_dependency_overrides(monkeypatch):
    mock_rag = MagicMock(spec=RagService)
    mock_evaluator = MagicMock(spec=EvaluatorService)

    def override_get_db():
        db = TestSessionLocal()
        try:
            yield db
        finally:
            db.close()

    fastapi_app.dependency_overrides[get_rag_service] = lambda: mock_rag
    fastapi_app.dependency_overrides[get_evaluator_service] = lambda: mock_evaluator
    fastapi_app.dependency_overrides[get_database_session] = override_get_db

    import app.api.endpoints.document
    import app.api.endpoints.history
    monkeypatch.setattr(app.api.endpoints.document, "get_database_session", override_get_db)
    monkeypatch.setattr(app.api.endpoints.evaluation, "get_database_session", override_get_db)
    monkeypatch.setattr(app.api.endpoints.history, "get_database_session", override_get_db)

    yield mock_rag, mock_evaluator

    fastapi_app.dependency_overrides.clear()


@pytest.fixture
def client():
    return TestClient(fastapi_app)


@pytest.fixture
def mock_rag(setup_dependency_overrides):
    return setup_dependency_overrides[0]


@pytest.fixture
def mock_evaluator(setup_dependency_overrides):
    return setup_dependency_overrides[1]
