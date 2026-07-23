from langgraph.graph import END, START, StateGraph

from app.logging import get_logger
from app.graph.nodes.converse import converse_node
from app.graph.nodes.evaluate import evaluate_polish_node
from app.graph.nodes.feedback import feedback_node
from app.graph.nodes.chinese_prevent import chinese_prevent_node
from app.graph.nodes.clean_polish_output import clean_polish_output_node
from app.graph.nodes.opening import opening_node
from app.graph.nodes.outline import outline_node
from app.graph.nodes.make_new_paper import make_new_paper_node
from app.graph.nodes.polish import polish_node
from app.graph.nodes.refuse import refuse_node
from app.graph.router.intent_router import route_by_action, router_node
from app.graph.state import GraphState

logger = get_logger(__name__)

MAX_POLISH_ATTEMPTS = 3
MIN_POLISH_RESULT_BYTES = 800


def route_after_chinese_prevent(state: GraphState) -> str:
    return "make_new_paper" if state.get("new_paper") else END


def route_after_polish(state: GraphState) -> str:
    new_paper = state.get("new_paper") or {}
    content = new_paper.get("content") or ""
    too_small = len(content.encode("utf-8")) < MIN_POLISH_RESULT_BYTES
    if too_small and state.get("polish_attempts", 0) < MAX_POLISH_ATTEMPTS:
        logger.info(
            "route_after_polish.retry",
            content_bytes=len(content.encode("utf-8")),
            attempt=state.get("polish_attempts", 0),
        )
        return "polish"
    return "chinese_prevent"


def build_graph(checkpointer):
    graph = StateGraph(GraphState)
    graph.add_node("router", router_node)
    graph.add_node("opening", opening_node)
    graph.add_node("converse", converse_node)
    graph.add_node("feedback", feedback_node)
    graph.add_node("outline", outline_node)
    graph.add_node("polish", polish_node)
    graph.add_node("clean_polish_output", clean_polish_output_node)
    graph.add_node("refuse", refuse_node)
    graph.add_node("chinese_prevent", chinese_prevent_node)
    graph.add_node("make_new_paper", make_new_paper_node)
    graph.add_node("evaluate_polish", evaluate_polish_node)

    graph.add_edge(START, "router")

    graph.add_conditional_edges(
        "router",
        route_by_action,
        {
            "opening": "opening",
            "say": "converse",
            "feedback": "feedback",
            "outline": "outline",
            "polish": "polish",
            "refuse": "refuse",
        },
    )

    for node_name in ("opening", "converse", "feedback", "outline", "refuse"):
        graph.add_edge(node_name, "chinese_prevent")

    graph.add_conditional_edges(
        "clean_polish_output",
        route_after_polish,
        {"polish": "polish", "chinese_prevent": "chinese_prevent"},
    )
    graph.add_edge("polish", "clean_polish_output")

    graph.add_conditional_edges(
        "chinese_prevent",
        route_after_chinese_prevent,
        {"make_new_paper": "make_new_paper", END: END},
    )
    graph.add_edge("make_new_paper", "evaluate_polish")
    graph.add_edge("evaluate_polish", END)
    return graph.compile(checkpointer=checkpointer)
