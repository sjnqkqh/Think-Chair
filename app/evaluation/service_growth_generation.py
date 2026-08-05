"""서비스 성장 평가용 응답 생성: 근거 주입 + converse/feedback 노드."""

from __future__ import annotations

import uuid
from collections.abc import Awaitable, Callable
from typing import Any

from langchain_core.messages import HumanMessage
from langgraph.graph import END, START, StateGraph

from app.evaluation.service_growth_contracts import ServiceGrowthCase
from app.graph.langfeather_tracing import apply_langfeather
from app.graph.nodes.converse import converse_node
from app.graph.nodes.feedback import feedback_node
from app.graph.state import GraphState
from app.research.turn_evidence import load_evidence_text_for_turn

EvidenceLoader = Callable[..., str]
GraphInvoker = Callable[..., Awaitable[dict[str, Any]]]


def build_service_growth_eval_graph(*, phase: str):
    """Route 없이 단일 대화 노드만 도는 얇은 그래프. LangFeather wrap 대상."""
    graph = StateGraph(GraphState)
    if phase == "feedback":
        graph.add_node("feedback", feedback_node)
        graph.add_edge(START, "feedback")
        graph.add_edge("feedback", END)
    else:
        graph.add_node("converse", converse_node)
        graph.add_edge(START, "converse")
        graph.add_edge("converse", END)
    return apply_langfeather(graph.compile())


def build_graph_state_for_case(
    case: ServiceGrowthCase,
    *,
    evidence_text: str,
    manuscript_id: str,
) -> GraphState:
    return {
        "manuscript_id": manuscript_id,
        "concept": case.concept,
        "topic": case.topic,
        "user_nickname": None,
        "audience_level": None,
        "user_action": case.phase,
        "current_message_id": None,
        "messages": [HumanMessage(content=case.claim)],
        "client_message": None,
        "new_paper": None,
        "document_generation_attempts": 0,
        "evidence_text": evidence_text or None,
    }


async def generate_service_growth_response(
    case: ServiceGrowthCase,
    *,
    user_id: uuid.UUID,
    manuscript_id: uuid.UUID,
    model: str = "default",
    load_evidence: EvidenceLoader = load_evidence_text_for_turn,
    invoke_graph: GraphInvoker | None = None,
) -> tuple[str, str]:
    """응답 본문과 주입된 근거 텍스트를 반환한다."""
    evidence_text = load_evidence(
        user_id=user_id,
        manuscript_id=manuscript_id,
        query=case.claim,
    )
    state = build_graph_state_for_case(
        case,
        evidence_text=evidence_text,
        manuscript_id=str(manuscript_id),
    )
    if invoke_graph is None:
        graph = build_service_growth_eval_graph(phase=case.phase)
        result = await graph.ainvoke(
            state,
            config={"configurable": {"model": model}},
        )
    else:
        result = await invoke_graph(
            state,
            config={"configurable": {"model": model}},
        )
    body = result.get("client_message") or ""
    if not isinstance(body, str):
        body = str(body)
    return body.strip(), evidence_text
