from unittest.mock import MagicMock

import pytest
from httpx import ASGITransport, AsyncClient
from langchain_core.language_models.fake_chat_models import FakeListChatModel

from app.graph import llm_registry
from app.graph.builder import build_graph
from app.graph.checkpointer import make_checkpointer
from app.pages.chat_pages import get_chat_service
from app.services.chat_service import ChatService
from main import app as fastapi_app


@pytest.fixture
async def e2e_chat_service(fake_llm, db_session):
    storage = MagicMock()
    async with make_checkpointer(":memory:") as checkpointer:
        graph = build_graph(checkpointer)
        svc = ChatService(graph=graph, storage=storage, db_factory=lambda: db_session)
        fastapi_app.dependency_overrides[get_chat_service] = lambda: svc
        yield svc, storage
        fastapi_app.dependency_overrides.pop(get_chat_service, None)


async def test_full_manuscript_flow(e2e_chat_service):
    svc, storage = e2e_chat_service

    # httpx.TestClient(동기 래퍼)는 요청마다 새 이벤트 루프를 띄우기 때문에,
    # AsyncSqliteSaver 내부 asyncio.Lock이 루프마다 재바인딩되며 깨진다.
    # 하나의 이벤트 루프 안에서 연속 요청을 보내야 하므로 httpx.AsyncClient + ASGITransport를 사용한다.
    transport = ASGITransport(app=fastapi_app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        # 1) 가입/로그인 (auth.py의 signup이 즉시 쿠키를 발급하므로 별도 로그인 호출 불필요)
        signup_res = await client.post(
            "/api/auth/signup",
            json={"login_id": "e2euser", "password": "password123", "nickname": "E2E"},
        )
        assert signup_res.status_code == 201

        # 2) 원고 생성
        create_res = await client.post(
            "/api/manuscripts", json={"topic": "RSC 회고", "concept": "tech_deepdive"}
        )
        assert create_res.status_code == 201
        manuscript_id = create_res.json()["id"]

        # 3) 메시지 3회 전송 → 체크포인트 누적 확인
        # fake_llm(고정 응답)이 router 분류 호출에도 그대로 쓰이므로 매번 "say"로 폴백 → converse 노드로 라우팅(정상)
        for i in range(3):
            r = await client.post(
                f"/api/chat/{manuscript_id}/message", data={"content": f"메시지 {i}"}
            )
            assert r.status_code == 200

        config = {"configurable": {"thread_id": manuscript_id}}
        snapshot = await svc.graph.aget_state(config)
        # HumanMessage 3 + AIMessage 3 = 6개 (fake_llm 고정 응답이므로 매번 동일 텍스트)
        assert len(snapshot.values["messages"]) == 6

        # 4) 초고 작성 요청 → 파일 저장 + DB row 확인
        # router 분류(1번째 LLM 호출) + draft_node 생성(2번째 호출)이 순서대로 소비되도록 전용 FakeListChatModel 등록
        original_llm = llm_registry._registry.get("default")
        llm_registry.register("default", FakeListChatModel(responses=["draft", "초고 본문입니다."]))
        try:
            draft_res = await client.post(
                f"/api/chat/{manuscript_id}/message", data={"content": "초고 작성해주세요"}
            )
            assert draft_res.status_code == 200
            # 파일 생성 시 본문 전체 대신 완료 안내만 채팅에 노출된다.
            assert "작성 완료되었습니다" in draft_res.text
            assert "초고 본문입니다" not in draft_res.text
        finally:
            if original_llm is not None:
                llm_registry.register("default", original_llm)
        storage.save.assert_called_once()

        # 5) 다른 원고의 thread_id 격리 확인
        create_res2 = await client.post(
            "/api/manuscripts", json={"topic": "다른 글", "concept": "til"}
        )
        manuscript_id2 = create_res2.json()["id"]
        config2 = {"configurable": {"thread_id": manuscript_id2}}
        snapshot2 = await svc.graph.aget_state(config2)
        assert not snapshot2.values or not snapshot2.values.get("messages")
