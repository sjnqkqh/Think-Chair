from unittest.mock import MagicMock

import pytest

from app.pages.chat_pages import get_chat_service
from app.graph.builder import build_graph
from app.graph.checkpointer import make_checkpointer
from app.services.chat_service import ChatService
from main import app as fastapi_app


def _signup_and_login(client, login_id="chattester"):
    client.post(
        "/api/auth/signup",
        json={"login_id": login_id, "password": "password123", "nickname": "테스터"},
    )


@pytest.fixture
async def chat_service_override(fake_llm, db_session):
    storage = MagicMock()
    async with make_checkpointer(":memory:") as checkpointer:
        graph = build_graph(checkpointer)
        svc = ChatService(graph=graph, storage=storage, db_factory=lambda: db_session)
        fastapi_app.dependency_overrides[get_chat_service] = lambda: svc
        yield svc
        fastapi_app.dependency_overrides.pop(get_chat_service, None)


def test_send_message_requires_auth(client, chat_service_override):
    response = client.post(
        "/api/chat/11111111-1111-1111-1111-111111111111/message",
        data={"content": "안녕하세요"},
    )
    assert response.status_code == 401


def test_send_message_returns_ai_response(client, chat_service_override):
    _signup_and_login(client)
    create_response = client.post(
        "/api/manuscripts", json={"topic": "FastAPI 학습", "concept": "til"}
    )
    manuscript_id = create_response.json()["id"]

    response = client.post(
        f"/api/chat/{manuscript_id}/message", data={"content": "안녕하세요"}
    )

    assert response.status_code == 200
    assert "테스트 응답입니다" in response.text
