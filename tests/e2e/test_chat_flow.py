import asyncio
import uuid

import pytest
from httpx import ASGITransport, AsyncClient
from langchain_core.language_models.fake_chat_models import FakeListChatModel

from app.graph import llm_registry
from app.models.chat import ChatMessage, RoutingDecision
from app.main import app as fastapi_app
from tests.helpers import join_sse_chunks, signup_async

pytestmark = pytest.mark.e2e


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


async def test_full_manuscript_flow(chat_app_state):
    graph, storage, db_session, _ = chat_app_state

    # httpx.TestClient(동기 래퍼)는 요청마다 새 이벤트 루프를 띄우기 때문에,
    # AsyncSqliteSaver 내부 asyncio.Lock이 루프마다 재바인딩되며 깨진다.
    # 하나의 이벤트 루프 안에서 연속 요청을 보내야 하므로 httpx.AsyncClient + ASGITransport를 사용한다.
    transport = ASGITransport(app=fastapi_app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        # 1) 가입/로그인 (auth.py의 signup이 즉시 쿠키를 발급하므로 별도 로그인 호출 불필요)
        signup_res = await signup_async(client, "e2euser", nickname="E2E")
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
        # router 분류(1번째) + 충분성 게이트(2번째 SUFFICIENT) + 문서 생성 노드(3번째)가
        # 순서대로 소비되도록 전용 FakeListChatModel 등록. 게이트 휴리스틱을 통과하도록
        # 충분한 길이의 요청 메시지를 보낸다.
        document_request = (
            "지금까지 이야기한 어텐션 메커니즘 내용을 바탕으로, RNN은 알지만 트랜스포머는 "
            "잘 모르고 있습니다. 추가 학습을 위한 딥다이브 원고를 작성해주세요. "
            "코드는 최소화하고 수식보다 비유와 예시 중심으로 설명해줘."
        )
        original_llm = llm_registry._registry.get("default")
        llm_registry.register(
            "default",
            FakeListChatModel(
                responses=[
                    "generate_document",
                    '{"sufficient": true, "reason": "근거 충분"}',
                    "원고 본문입니다.",
                ]
            ),
        )
        try:
            document_res = await client.post(
                f"/api/chat/{manuscript_id}/message",
                data={"content": document_request},
            )
            assert document_res.status_code == 200
            # 파일 생성은 분리되어 즉시 시작 안내만 채팅에 노출된다.
            assert join_sse_chunks(document_res.text) == (
                "문서 작성을 시작했습니다. 완료되면 오른쪽 문서 목록에 표시됩니다."
            )
            assert "원고 본문입니다" not in document_res.text
            await _wait_until(lambda: storage.save.assert_called_once())
        finally:
            if original_llm is not None:
                llm_registry.register("default", original_llm)
        chat_messages_after_document_generation = (
            db_session
            .query(ChatMessage)
            .filter(ChatMessage.manuscript_id == manuscript_uuid)
            .order_by(ChatMessage.sequence.asc())
            .all()
        )
        assert len(chat_messages_after_document_generation) == 8
        assert chat_messages_after_document_generation[-2].content == document_request
        assert chat_messages_after_document_generation[-1].role == "assistant"
        assert chat_messages_after_document_generation[-1].phase == "generate_document"

        routing_decisions_after_document_generation = (
            db_session
            .query(RoutingDecision)
            .filter(RoutingDecision.manuscript_id == manuscript_uuid)
            .order_by(RoutingDecision.created_at.asc())
            .all()
        )
        assert len(routing_decisions_after_document_generation) == 4
        assert routing_decisions_after_document_generation[-1].decision == "generate_document"
        assert routing_decisions_after_document_generation[-1].raw_output == "generate_document"

        # 5) 문서화 완료 뒤의 일반 질문은 say로 처리한다. 생성한 원고 본문은
        # 그래프 대화 컨텍스트에 넣지 않고, 완료 상태 AI 메시지만 남겨야 한다.
        llm_registry.register(
            "default",
            FakeListChatModel(
                responses=[
                    "say|포스팅 요약 아이디어를 묻는 일반 대화",
                    "포스팅 요약은 AI 에이전트 중심 서버 설계의 핵심과 한계를 짚는 내용으로 적을 수 있습니다.",
                ]
            ),
        )
        try:
            summary_res = await client.post(
                f"/api/chat/{manuscript_id}/message",
                data={"content": "이 대화를 포스팅으로 작성한다면 요약을 뭐라고 적으면 좋을까요?"},
            )
            assert summary_res.status_code == 200
            summary = join_sse_chunks(summary_res.text)
            assert summary == (
                "포스팅 요약은 AI 에이전트 중심 서버 설계의 핵심과 한계를 짚는 내용으로 적을 수 있습니다."
            )
            assert "원고 본문입니다." not in summary

            snapshot = await graph.aget_state(config)
            history = snapshot.values["messages"]
            assert any(
                message.content
                == "문서 생성과 저장이 완료되었습니다. 문서 본문은 대화 컨텍스트에 포함하지 않습니다."
                for message in history
            )
            assert all(message.content != "원고 본문입니다." for message in history)
        finally:
            if original_llm is not None:
                llm_registry.register("default", original_llm)

        # 6) 다른 원고의 thread_id 격리 확인
        create_res2 = await client.post(
            "/api/manuscripts", json={"topic": "다른 글", "concept": "TIL"}
        )
        manuscript_id2 = create_res2.json()["id"]
        config2 = {"configurable": {"thread_id": manuscript_id2}}
        snapshot2 = await graph.aget_state(config2)
        assert not snapshot2.values or not snapshot2.values.get("messages")
