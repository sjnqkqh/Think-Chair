import asyncio
import json
import uuid
from unittest.mock import MagicMock

import pytest
from httpx import ASGITransport, AsyncClient
from langchain_core.language_models.fake_chat_models import FakeListChatModel

from app.graph import llm_registry
from app.graph.builder import build_graph
from app.graph.chat_graph_runner import ChatGraphRunner
from app.graph.checkpointer import make_checkpointer
from app.models.chat import ChatMessage, RoutingDecision
from app.services.background_tasks import BackgroundTaskRegistry
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


async def _wait_until(assertion, timeout: float = 1.0):
    deadline = asyncio.get_running_loop().time() + timeout
    while True:
        try:
            assertion()
            return
        except AssertionError:
            if asyncio.get_running_loop().time() >= deadline:
                raise
            await asyncio.sleep(0.02)


@pytest.fixture
async def fake_chat_runtime(fake_llm, db_session):
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
        previous_chat_service = getattr(fastapi_app.state, "chat_service", None)
        had_previous_chat_service = hasattr(fastapi_app.state, "chat_service")
        fastapi_app.state.chat_service = chat_service
        try:
            yield graph, storage, db_session
        finally:
            if had_previous_chat_service:
                fastapi_app.state.chat_service = previous_chat_service
            else:
                del fastapi_app.state.chat_service


async def test_full_manuscript_flow(fake_chat_runtime):
    graph, storage, db_session = fake_chat_runtime

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
            "/api/manuscripts", json={"topic": "RSC 회고", "concept": "딥다이브"}
        )
        assert create_res.status_code == 201
        manuscript_id = create_res.json()["id"]
        manuscript_uuid = uuid.UUID(manuscript_id)

        # 3) 메시지 3회 전송 → 체크포인트 누적 확인
        # fake_llm(고정 응답)이 router 분류 호출에도 그대로 쓰이므로 매번 "say"로 폴백 → converse 노드로 라우팅(정상)
        for i in range(3):
            r = await client.post(
                f"/api/chat/{manuscript_id}/message", data={"content": f"메시지 {i}"}
            )
            assert r.status_code == 200

        config = {"configurable": {"thread_id": manuscript_id}}
        snapshot = await graph.aget_state(config)
        # HumanMessage 3 + AIMessage 3 = 6개 (fake_llm 고정 응답이므로 매번 동일 텍스트)
        assert len(snapshot.values["messages"]) == 6
        chat_messages = (
            db_session
            .query(ChatMessage)
            .filter(ChatMessage.manuscript_id == manuscript_uuid)
            .order_by(ChatMessage.sequence.asc())
            .all()
        )
        assert [message.role for message in chat_messages] == [
            "user",
            "assistant",
            "user",
            "assistant",
            "user",
            "assistant",
        ]
        assert [message.sequence for message in chat_messages] == [1, 2, 3, 4, 5, 6]
        assert chat_messages[0].content == "메시지 0"
        assert chat_messages[1].phase == "opening"

        routing_decisions = (
            db_session
            .query(RoutingDecision)
            .filter(RoutingDecision.manuscript_id == manuscript_uuid)
            .order_by(RoutingDecision.created_at.asc())
            .all()
        )
        assert [decision.router_name for decision in routing_decisions] == [
            "intent",
            "intent",
            "intent",
        ]
        assert [decision.decision for decision in routing_decisions] == [
            "opening",
            "say",
            "say",
        ]
        assert routing_decisions[0].message_id == chat_messages[0].id

        # 4) 원고 작성 요청 → 파일 저장 + DB row 확인
        # router 분류(1번째 LLM 호출) + polish_node 생성(2번째 호출)이 순서대로 소비되도록 전용 FakeListChatModel 등록
        original_llm = llm_registry._registry.get("default")
        llm_registry.register(
            "default", FakeListChatModel(responses=["polish", "원고 본문입니다."])
        )
        try:
            polish_res = await client.post(
                f"/api/chat/{manuscript_id}/message",
                data={"content": "원고 작성해주세요"},
            )
            assert polish_res.status_code == 200
            # 파일 생성은 분리되어 즉시 시작 안내만 채팅에 노출된다.
            assert _joined_sse_chunks(polish_res.text) == (
                "문서 작성을 시작했습니다. 완료되면 오른쪽 문서 목록에 표시됩니다."
            )
            assert "원고 본문입니다" not in polish_res.text
            await _wait_until(lambda: storage.save.assert_called_once())
        finally:
            if original_llm is not None:
                llm_registry.register("default", original_llm)
        chat_messages_after_polish = (
            db_session
            .query(ChatMessage)
            .filter(ChatMessage.manuscript_id == manuscript_uuid)
            .order_by(ChatMessage.sequence.asc())
            .all()
        )
        assert len(chat_messages_after_polish) == 8
        assert chat_messages_after_polish[-2].content == "원고 작성해주세요"
        assert chat_messages_after_polish[-1].role == "assistant"
        assert chat_messages_after_polish[-1].phase == "polish"

        routing_decisions_after_polish = (
            db_session
            .query(RoutingDecision)
            .filter(RoutingDecision.manuscript_id == manuscript_uuid)
            .order_by(RoutingDecision.created_at.asc())
            .all()
        )
        assert len(routing_decisions_after_polish) == 4
        assert routing_decisions_after_polish[-1].decision == "polish"
        assert routing_decisions_after_polish[-1].raw_output == "polish"

        # 5) 다른 원고의 thread_id 격리 확인
        create_res2 = await client.post(
            "/api/manuscripts", json={"topic": "다른 글", "concept": "TIL"}
        )
        manuscript_id2 = create_res2.json()["id"]
        config2 = {"configurable": {"thread_id": manuscript_id2}}
        snapshot2 = await graph.aget_state(config2)
        assert not snapshot2.values or not snapshot2.values.get("messages")
