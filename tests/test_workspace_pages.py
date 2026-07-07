import uuid
from unittest.mock import AsyncMock, MagicMock

from httpx import ASGITransport, AsyncClient

from app.graph.builder import build_graph
from app.graph.checkpointer import make_checkpointer
from app.pages.chat_pages import get_chat_service
from app.services.chat_service import ChatService
from main import app as fastapi_app


def _signup_and_login(client, login_id="workspacetester"):
    client.post(
        "/api/auth/signup",
        json={"login_id": login_id, "password": "password123", "nickname": "테스터"},
    )


def test_workspace_root_requires_auth(client):
    response = client.get("/workspace", follow_redirects=False)
    assert response.status_code == 303


def test_workspace_detail_requires_auth(client):
    response = client.get(f"/workspace/{uuid.uuid4()}", follow_redirects=False)
    assert response.status_code == 303


def test_workspace_root_renders_new_manuscript_button(client):
    _signup_and_login(client)
    response = client.get("/workspace")
    assert response.status_code == 200
    assert "새 원고" in response.text
    assert 'aria-label="모달 닫기"' in response.text
    assert '@click.self="open = false"' in response.text
    assert '@keydown.escape.window="open = false"' in response.text


def test_workspace_detail_does_not_render_draft_prompt_button(client):
    _signup_and_login(client, login_id=f"workspacetester-{uuid.uuid4()}")
    create_response = client.post(
        "/api/manuscripts", json={"topic": "워크스페이스", "concept": "til"}
    )
    manuscript_id = create_response.json()["id"]

    chat_service = MagicMock()
    chat_service.graph.aget_state = AsyncMock(return_value=MagicMock(values={}))
    fastapi_app.state.chat_service = chat_service
    try:
        response = client.get(f"/workspace/{manuscript_id}")
        assert response.status_code == 200
        assert "초고 작성" not in response.text
        assert "개요 생성" in response.text
        assert "탈고" in response.text
    finally:
        del fastapi_app.state.chat_service


def test_workspace_detail_unknown_manuscript_returns_404(client):
    _signup_and_login(client, login_id="workspacetester2")
    response = client.get(f"/workspace/{uuid.uuid4()}")
    assert response.status_code == 404


async def test_workspace_detail_reload_with_history_renders_messages(fake_llm, db_session):
    # 회귀 테스트: _chat_center.html의 for 루프 변수명이 _message.html이 기대하는
    # "message"와 달라 대화 이력이 있는 상태로 새로고침하면 500이 발생했었다.
    storage = MagicMock()
    async with make_checkpointer(":memory:") as checkpointer:
        graph = build_graph(checkpointer)
        svc = ChatService(graph=graph, storage=storage, db_factory=lambda: db_session)
        fastapi_app.dependency_overrides[get_chat_service] = lambda: svc
        fastapi_app.state.chat_service = svc
        try:
            transport = ASGITransport(app=fastapi_app)
            async with AsyncClient(transport=transport, base_url="http://testserver") as client:
                await client.post(
                    "/api/auth/signup",
                    json={
                        "login_id": "workspacereload",
                        "password": "password123",
                        "nickname": "테스터",
                    },
                )
                create_res = await client.post(
                    "/api/manuscripts", json={"topic": "재현", "concept": "til"}
                )
                manuscript_id = create_res.json()["id"]

                msg_res = await client.post(
                    f"/api/chat/{manuscript_id}/message", data={"content": "안녕하세요"}
                )
                assert msg_res.status_code == 200

                reload_res = await client.get(f"/workspace/{manuscript_id}")
                assert reload_res.status_code == 200
                assert "안녕하세요" in reload_res.text
                assert "테스트 응답입니다" in reload_res.text
        finally:
            fastapi_app.dependency_overrides.pop(get_chat_service, None)
            del fastapi_app.state.chat_service
