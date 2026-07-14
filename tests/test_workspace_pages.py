import datetime
import uuid
from unittest.mock import AsyncMock, MagicMock

from httpx import ASGITransport, AsyncClient

from app.graph.builder import build_graph
from app.graph.checkpointer import make_checkpointer
from app.models.manuscript import ManuscriptVersion
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
    assert "Think Chair" in response.text
    assert "/static/common/think_chair_icon.jpg" in response.text
    assert '<strong class="font-bold">주도성 상실</strong>' in response.text
    assert '<strong class="font-bold">끊임없이 질문을 던지며 사용자의 생각을 끌어내는 AI</strong>' in response.text
    assert '<strong class="font-bold">사용자가 안다고 생각했던 개념과 아직 설명하지 못하는 개념을 구분</strong>' in response.text
    assert '<strong class="font-bold">지식의 밑바닥</strong>' in response.text
    assert "답을 대신 내놓는 AI가 아니라" in response.text
    assert "논리적 빈틈과 불명확한 지점" in response.text
    assert "로그아웃" in response.text
    assert "grid-cols-[16rem_minmax(0,1fr)_14rem]" in response.text
    assert "새 원고" in response.text
    assert 'aria-label="모달 닫기"' in response.text
    assert '@click.self="open = false"' in response.text
    assert '@keydown.escape.window="open = false"' in response.text
    assert "::selection { background-color: #bfdbfe; color: #111827; }" in response.text


def test_workspace_detail_renders_version_download_label(client, db_session):
    _signup_and_login(client, login_id=f"workspaceversion-{uuid.uuid4()}")
    create_response = client.post(
        "/api/manuscripts", json={"topic": "버전 표시", "concept": "TIL"}
    )
    manuscript_id = uuid.UUID(create_response.json()["id"])
    db_session.add_all(
        [
            ManuscriptVersion(
                manuscript_id=manuscript_id,
                kind="outline",
                revision=1,
                storage_key="outlines/test.md",
                created_at=datetime.datetime(2026, 7, 8, 0, 6),
            ),
            ManuscriptVersion(
                manuscript_id=manuscript_id,
                kind="polish",
                revision=1,
                storage_key="polishs/test.md",
                created_at=datetime.datetime(2026, 7, 8, 0, 7),
            ),
        ]
    )
    db_session.commit()

    chat_service = MagicMock()
    chat_service.graph.aget_state = AsyncMock(return_value=MagicMock(values={}))
    fastapi_app.state.chat_service = chat_service
    try:
        response = client.get(f"/workspace/{manuscript_id}")
        assert response.status_code == 200
        assert "개요 1" in response.text
        assert "문서 1" in response.text
        assert "버전 1" not in response.text
        assert 'class="text-sm text-[#787671]">(09:07)</span>' in response.text
        assert "[다운로드]" in response.text
        assert "polish v1" not in response.text
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
        previous = getattr(fastapi_app.state, "chat_service", None)
        had_previous = hasattr(fastapi_app.state, "chat_service")
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
                    "/api/manuscripts", json={"topic": "재현", "concept": "TIL"}
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
            if had_previous:
                fastapi_app.state.chat_service = previous
            else:
                del fastapi_app.state.chat_service
