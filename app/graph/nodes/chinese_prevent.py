from langchain_core.messages import AIMessage

from app.core.chinese_filter import sanitize_chinese
from app.graph.state import GraphState


def chinese_prevent_node(state: GraphState) -> dict:
    patch: dict = {}
    last = state["messages"][-1] if state["messages"] else None
    if isinstance(last, AIMessage) and last.content:
        clean = sanitize_chinese(last.content)
        if clean != last.content:
            patch["messages"] = [AIMessage(content=clean, id=last.id)]

    new_paper = state.get("new_paper")
    if new_paper and new_paper.get("content"):
        patch["new_paper"] = {**new_paper, "content": sanitize_chinese(new_paper["content"])}

    return patch
