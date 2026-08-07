"""research_required 답변 보류 → continue 근거 반영 스트리밍 e2e.

httpx.TestClient(동기)는 요청마다 새 이벤트 루프를 띄워 AsyncSqliteSaver의
asyncio.Lock이 깨지므로, 여러 턴을 잇는 시나리오는 AsyncClient + ASGITransport로
하나의 이벤트 루프 안에서 실행한다(tests/e2e/test_chat_flow.py와 동일한 이유).
"""

import json
import uuid

import pytest
from httpx import ASGITransport, AsyncClient
from langchain_core.language_models.fake_chat_models import FakeListChatModel

from app.llm import registry as llm_registry
from app.main import app as fastapi_app
from app.models.chat import ChatMessage
from app.models.manuscript import Manuscript
from app.models.research import ResearchJob, ResearchJobStatus
from tests.helpers import join_sse_chunks, signup_async

pytestmark = pytest.mark.e2e

CLAIM = "보통 CPU 점유율을 봅니다."


def _parse_sse_blocks(body: str) -> list[str]:
    return [block for block in body.strip().split("\n\n") if block.strip()]


async def test_research_required_withholds_reply_then_continue_delivers_grounded_answer(
    chat_app_state, monkeypatch
):
    """research_required 턴은 답변을 보류하고, 조사 완료 후 continue가 같은 턴에 답한다."""
    _, _, db_session, _ = chat_app_state

    monkeypatch.setattr(
        "app.research.turn_evidence.evidence_sufficient_for_turn",
        lambda **_kwargs: False,
    )

    transport = ASGITransport(app=fastapi_app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        signup_res = await signup_async(client, "continue-e2e-user")
        assert signup_res.status_code == 201

        create_res = await client.post(
            "/api/manuscripts", json={"topic": "RSC 회고", "concept": "딥다이브"}
        )
        assert create_res.status_code == 201
        manuscript_id = create_res.json()["id"]

        original_llm = llm_registry._registry.get("default")

        # 1턴: 오프닝(분류 호출 없음, opening_node LLM 호출 1회)
        llm_registry.register(
            "default", FakeListChatModel(responses=["오프닝 응답입니다."])
        )
        opening_res = await client.post(
            f"/api/chat/{manuscript_id}/message", data={"content": "안녕하세요"}
        )
        assert opening_res.status_code == 200

        # 2턴: 일반론 주장 → research_required, 답변은 보류(chunk 없음)
        llm_registry.register(
            "default", FakeListChatModel(responses=["say|일반론 주장"])
        )
        claim_res = await client.post(
            f"/api/chat/{manuscript_id}/message", data={"content": CLAIM}
        )
        assert claim_res.status_code == 200
        blocks = _parse_sse_blocks(claim_res.text)
        assert any("event: research_required" in block for block in blocks)
        assert not any("event: chunk" in block for block in blocks)
        done_block = next(block for block in blocks if "event: done" in block)
        assert '"awaiting_research": true' in done_block

        research_block = next(
            block for block in blocks if "event: research_required" in block
        )
        message_id = uuid.UUID(
            json.loads(research_block.split("data: ", 1)[1])["message_id"]
        )

        # 조사가 완료된 것처럼 job을 직접 만든다(웹 조사 실행 자체는 이 테스트 범위 밖).
        manuscript = db_session.get(Manuscript, uuid.UUID(manuscript_id))
        job = ResearchJob(
            id=uuid.uuid4(),
            user_id=manuscript.user_id,
            manuscript_id=manuscript.id,
            message_id=message_id,
            claim_or_query=CLAIM,
            status=ResearchJobStatus.COMPLETED,
        )
        db_session.add(job)
        db_session.commit()

        # continue: 같은 턴에 근거를 반영한 답변을 이어 스트리밍한다.
        llm_registry.register(
            "default", FakeListChatModel(responses=["근거를 반영한 답변입니다."])
        )
        continue_res = await client.post(
            f"/api/research/jobs/{job.id}/continue",
            json={"manuscript_id": manuscript_id, "message_id": str(message_id)},
        )
        if original_llm is not None:
            llm_registry.register("default", original_llm)

        assert continue_res.status_code == 200
        assert join_sse_chunks(continue_res.text) == "근거를 반영한 답변입니다."

        chat_messages = (
            db_session.query(ChatMessage)
            .filter(ChatMessage.manuscript_id == uuid.UUID(manuscript_id))
            .order_by(ChatMessage.sequence.asc())
            .all()
        )
        user_messages = [m for m in chat_messages if m.role == "user"]
        # 오프닝 + 주장. continue는 begin_turn을 다시 부르지 않으므로 중복 저장되지 않는다.
        assert len(user_messages) == 2
        assert chat_messages[-1].role == "assistant"
        assert chat_messages[-1].content == "근거를 반영한 답변입니다."
        assert chat_messages[-1].phase == "say"
