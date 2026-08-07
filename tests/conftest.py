import os

os.environ["LANGCHAIN_TRACING_V2"] = "false"
os.environ["LANGSMITH_TRACING"] = "false"
# 단위/통합 테스트는 실 LLM 기동 검증을 하지 않는다.
os.environ["LLM_STARTUP_VERIFY"] = "false"

from collections import namedtuple
from contextlib import contextmanager
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient
from langchain_core.language_models.fake_chat_models import FakeListChatModel
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.database import Base, get_database_session
from app.llm import registry as llm_registry
from app.graph.builder import build_graph
from app.graph.chat_graph_runner import ChatGraphRunner
from app.graph.checkpointer import make_checkpointer
from app.services.background_tasks import BackgroundTaskRegistry
from app.services.chat_service import ChatService
from app.main import app as fastapi_app
from tests.db_setup import prepare_test_database

test_engine = create_engine(
    "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
)
TestSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)
prepare_test_database(test_engine)


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


@contextmanager
def _override_app_state(**attributes):
    """fastapi_app.state의 속성을 임시로 교체하고, 블록 종료 시 원상 복구한다."""
    sentinel = object()
    previous = {
        name: getattr(fastapi_app.state, name, sentinel) for name in attributes
    }
    for name, value in attributes.items():
        setattr(fastapi_app.state, name, value)
    try:
        yield
    finally:
        for name, prior in previous.items():
            if prior is sentinel:
                delattr(fastapi_app.state, name)
            else:
                setattr(fastapi_app.state, name, prior)


ChatAppState = namedtuple("ChatAppState", ["graph", "storage", "db_session", "chat_service"])


@pytest.fixture
async def chat_app_state(fake_llm, db_session, monkeypatch):
    """실 그래프로 배선한 ChatService를 app.state에 얹는다.

    chat API·e2e 흐름·워크스페이스 재로드 테스트가 공유하는 배선.
    FakeList LLM 경로이므로 턴 근거 검색(OpenAI embeddings)은 호출하지 않는다.
    """
    monkeypatch.setattr(
        "app.research.turn_evidence.load_evidence_text_for_turn",
        lambda **_kwargs: "",
    )
    # 원고 LLM 설정이 있어도 FakeListChatModel("default")만 쓰게 한다.
    monkeypatch.setattr(
        llm_registry,
        "chat_model_key_for",
        lambda **_kwargs: "default",
    )
    storage = MagicMock()
    async with make_checkpointer(":memory:") as checkpointer:
        graph = build_graph(checkpointer)
        graph_runner = ChatGraphRunner(
            graph=graph, storage=storage, db_factory=lambda: db_session
        )
        chat_service = ChatService(
            graph_runner=graph_runner,
            db_factory=lambda: db_session,
            background_tasks=BackgroundTaskRegistry(),
        )
        with _override_app_state(chat_service=chat_service):
            yield ChatAppState(graph, storage, db_session, chat_service)
