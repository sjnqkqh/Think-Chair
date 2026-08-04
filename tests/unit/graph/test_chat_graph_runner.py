from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.graph.chat_graph_runner import ChatGraphRunner

pytestmark = pytest.mark.unit


@pytest.mark.asyncio
async def test_route_turn_passes_evidence_text_into_graph_state():
    captured = {}

    class FakeGraph:
        async def ainvoke(self, state, **_kwargs):
            captured["state"] = state
            return {"user_action": "say"}

    user = SimpleNamespace(nickname="n")
    manuscript = SimpleNamespace(
        id=uuid4(),
        user_id=uuid4(),
        topic="topic",
        concept=SimpleNamespace(value="딥다이브"),
        audience_level=None,
    )
    runner = ChatGraphRunner(graph=FakeGraph(), storage=None, db_factory=None)
    state = await runner.route_turn(
        manuscript=manuscript,
        user=user,
        user_message="다음 질문",
        user_message_id=uuid4(),
        request_db_session=None,
        model="default",
        evidence_text="참고 자료 본문",
    )

    assert state["user_action"] == "say"
    assert captured["state"]["evidence_text"] == "참고 자료 본문"
