from langgraph.graph import END, START, StateGraph

from app.graph.nodes.converse import converse_node
from app.graph.nodes.feedback import feedback_node
from app.graph.nodes.finalize import finalize_node
from app.graph.nodes.chinese_prevent import chinese_prevent_node
from app.graph.nodes.opening import opening_node
from app.graph.nodes.outline import outline_node
from app.graph.nodes.make_new_paper import make_new_paper_node
from app.graph.nodes.polish import polish_node
from app.graph.router.intent_router import route_by_action, router_node
from app.graph.state import GraphState


def route_after_chinese_prevent(state: GraphState) -> str:
    return "make_new_paper" if state.get("new_paper") else END


def build_graph(checkpointer):
    graph = StateGraph(GraphState)
    graph.add_node("router", router_node)
    graph.add_node("opening", opening_node)
    graph.add_node("converse", converse_node)
    graph.add_node("feedback", feedback_node)
    graph.add_node("outline", outline_node)
    graph.add_node("polish", polish_node)
    graph.add_node("finalize", finalize_node)
    graph.add_node("chinese_prevent", chinese_prevent_node)
    graph.add_node("make_new_paper", make_new_paper_node)

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
            "finalize": "finalize",
        },
    )

    for node_name in ("opening", "converse", "feedback", "outline", "polish"):
        graph.add_edge(node_name, "chinese_prevent")

    graph.add_conditional_edges(
        "chinese_prevent",
        route_after_chinese_prevent,
        {"make_new_paper": "make_new_paper", END: END},
    )
    graph.add_edge("make_new_paper", END)
    graph.add_edge("finalize", END)

    return graph.compile(checkpointer=checkpointer)
