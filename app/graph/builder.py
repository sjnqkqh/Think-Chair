from langgraph.graph import END, START, StateGraph

from app.logging import get_logger
from app.graph.nodes.converse import converse_node
from app.graph.nodes.evaluate import evaluate_document_node
from app.graph.nodes.feedback import feedback_node
from app.graph.nodes.chinese_prevent import chinese_prevent_node
from app.graph.nodes.opening import opening_node
from app.graph.nodes.outline import outline_node
from app.graph.nodes.save_new_paper import save_new_paper_node
from app.graph.nodes.generate_document_from_conversation import (
    generate_document_from_conversation_node,
)
from app.graph.nodes.reject_documentation import reject_documentation_node
from app.graph.router.intent_router import route_by_action, router_node
from app.graph.state import GraphState

logger = get_logger(__name__)

MAX_DOCUMENT_GENERATION_ATTEMPTS = 3
MIN_DOCUMENT_RESULT_BYTES = 800


def route_after_chinese_prevent(state: GraphState) -> str:
    return "save_new_paper" if state.get("new_paper") else END


def route_after_generate_document_from_conversation(state: GraphState) -> str:
    new_paper = state.get("new_paper") or {}
    content = new_paper.get("content") or ""
    too_small = len(content.encode("utf-8")) < MIN_DOCUMENT_RESULT_BYTES
    if (
        too_small
        and state.get("document_generation_attempts", 0)
        < MAX_DOCUMENT_GENERATION_ATTEMPTS
    ):
        logger.info(
            "route_after_generate_document_from_conversation.retry",
            content_bytes=len(content.encode("utf-8")),
            attempt=state.get("document_generation_attempts", 0),
        )
        return "generate_document_from_conversation"
    return "chinese_prevent"


def build_graph(checkpointer):
    graph = StateGraph(GraphState)
    graph.add_node("router", router_node)
    graph.add_node("opening", opening_node)
    graph.add_node("converse", converse_node)
    graph.add_node("feedback", feedback_node)
    graph.add_node("outline", outline_node)
    graph.add_node(
        "generate_document_from_conversation",
        generate_document_from_conversation_node,
    )
    graph.add_node("reject_documentation", reject_documentation_node)
    graph.add_node("chinese_prevent", chinese_prevent_node)
    graph.add_node("save_new_paper", save_new_paper_node)
    graph.add_node("evaluate_document", evaluate_document_node)

    graph.add_edge(START, "router")

    graph.add_conditional_edges(
        "router",
        route_by_action,
        {
            "opening": "opening",
            "say": "converse",
            "feedback": "feedback",
            "outline": "outline",
            "generate_document": "generate_document_from_conversation",
            "refuse": "reject_documentation",
        },
    )

    for node_name in ("opening", "converse", "feedback", "outline"):
        graph.add_edge(node_name, "chinese_prevent")
    graph.add_edge("reject_documentation", END)

    graph.add_conditional_edges(
        "generate_document_from_conversation",
        route_after_generate_document_from_conversation,
        {
            "generate_document_from_conversation": "generate_document_from_conversation",
            "chinese_prevent": "chinese_prevent",
        },
    )

    graph.add_conditional_edges(
        "chinese_prevent",
        route_after_chinese_prevent,
        {"save_new_paper": "save_new_paper", END: END},
    )
    graph.add_edge("save_new_paper", "evaluate_document")
    graph.add_edge("evaluate_document", END)
    return graph.compile(checkpointer=checkpointer)
