import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.evaluation.service_growth_contracts import ServiceGrowthCase
from app.evaluation.service_growth_generation import (
    build_graph_state_for_case,
    build_service_growth_eval_graph,
    generate_service_growth_response,
)

pytestmark = pytest.mark.unit


def _case(phase: str = "say") -> ServiceGrowthCase:
    return ServiceGrowthCase.model_validate(
        {
            "case_id": "c1",
            "phase": phase,
            "language": "ko",
            "claim": "RAG를 사용하면 품질이 좋아진다.",
            "concept": "딥다이브",
            "topic": "RAG",
        }
    )


def test_build_graph_state_includes_claim_and_evidence():
    state = build_graph_state_for_case(
        _case(),
        evidence_text="근거 텍스트",
        manuscript_id="ms-1",
    )
    assert state["user_action"] == "say"
    assert state["evidence_text"] == "근거 텍스트"
    assert state["messages"][0].content == "RAG를 사용하면 품질이 좋아진다."


@pytest.mark.asyncio
async def test_generate_uses_evidence_loader_and_graph_invoker():
    invoke_graph = AsyncMock(
        return_value={"client_message": "구체적 응답입니다."}
    )
    body, evidence = await generate_service_growth_response(
        _case(),
        user_id=uuid.uuid4(),
        manuscript_id=uuid.uuid4(),
        load_evidence=lambda **_: "injected",
        invoke_graph=invoke_graph,
    )
    assert body == "구체적 응답입니다."
    assert evidence == "injected"
    invoke_graph.assert_awaited_once()


def test_build_eval_graph_applies_langfeather_when_enabled(monkeypatch):
    compiled = MagicMock(name="compiled")
    wrapped = MagicMock(name="wrapped")
    compile_mock = MagicMock(return_value=compiled)

    class FakeGraph:
        def add_node(self, *args, **kwargs):
            return None

        def add_edge(self, *args, **kwargs):
            return None

        def compile(self):
            return compile_mock()

    monkeypatch.setattr(
        "app.evaluation.service_growth_generation.StateGraph",
        lambda *_a, **_k: FakeGraph(),
    )
    monkeypatch.setattr(
        "app.evaluation.service_growth_generation.apply_langfeather",
        lambda graph: wrapped if graph is compiled else graph,
    )

    result = build_service_growth_eval_graph(phase="feedback")
    assert result is wrapped
