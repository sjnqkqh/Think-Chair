import json
from unittest.mock import MagicMock

import pytest

from app.graph.builder import build_graph
from app.graph.checkpointer import make_checkpointer
from app.services.chat_service import ChatService
from main import app as fastapi_app


def _joined_sse_chunks(body: str) -> str:
    chunks = []
    for event in body.strip().split("\n\n"):
        if "\nevent: chunk\n" not in f"\n{event}\n":
            continue
        data = event.split("data: ", 1)[1]
        chunks.append(json.loads(data)["content"])
    return "".join(chunks)


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
        previous = getattr(fastapi_app.state, "chat_service", None)
        had_previous = hasattr(fastapi_app.state, "chat_service")
        fastapi_app.state.chat_service = svc
        try:
            yield svc
        finally:
            if had_previous:
                fastapi_app.state.chat_service = previous
            else:
                del fastapi_app.state.chat_service


def test_send_message_requires_auth(client, chat_service_override):
    response = client.post(
        "/api/chat/11111111-1111-1111-1111-111111111111/message",
        data={"content": "안녕하세요"},
    )
    assert response.status_code == 401


def test_send_message_returns_ai_response(client, chat_service_override):
    _signup_and_login(client)
    create_response = client.post(
        "/api/manuscripts", json={"topic": "FastAPI 학습", "concept": "TIL"}
    )
    manuscript_id = create_response.json()["id"]

    response = client.post(
        f"/api/chat/{manuscript_id}/message", data={"content": "안녕하세요"}
    )

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    assert _joined_sse_chunks(response.text) == "테스트 응답입니다."
