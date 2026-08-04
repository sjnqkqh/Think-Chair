import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.evaluation.service_growth_contracts import ServiceGrowthCase
from app.evaluation.service_growth_generation import (
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


@pytest.mark.asyncio
async def test_generate_passes_loaded_evidence_into_graph_state():
    invoke_graph = AsyncMock(return_value={"client_message": "응답"})
    body, evidence = await generate_service_growth_response(
        _case(),
        user_id=uuid.uuid4(),
        manuscript_id=uuid.uuid4(),
        load_evidence=lambda **_: "injected-evidence",
        invoke_graph=invoke_graph,
    )
    assert body == "응답"
    assert evidence == "injected-evidence"
    state = invoke_graph.await_args.args[0]
    assert state["evidence_text"] == "injected-evidence"
    assert state["user_action"] == "say"
    assert state["messages"][0].content == "RAG를 사용하면 품질이 좋아진다."


def test_eval_graph_is_wrapped_with_langfeather(monkeypatch):
    compiled = MagicMock(name="compiled")
    wrapped = MagicMock(name="wrapped")

    class FakeGraph:
        def add_node(self, *args, **kwargs):
            return None

        def add_edge(self, *args, **kwargs):
            return None

        def compile(self):
            return compiled

    monkeypatch.setattr(
        "app.evaluation.service_growth_generation.StateGraph",
        lambda *_a, **_k: FakeGraph(),
    )
    monkeypatch.setattr(
        "app.evaluation.service_growth_generation.apply_langfeather",
        lambda graph: wrapped if graph is compiled else graph,
    )
    assert build_service_growth_eval_graph(phase="feedback") is wrapped
