from langchain_core.messages import AIMessage

from app.core.chinese_filter import sanitize_chinese
from app.graph.state import DraftsmithState


def chinese_prevent_node(state: DraftsmithState) -> dict:
    patch: dict = {}
    last = state["messages"][-1] if state["messages"] else None
    if isinstance(last, AIMessage) and last.content:
        clean = sanitize_chinese(last.content)
        if clean != last.content:
            patch["messages"] = [AIMessage(content=clean, id=last.id)]

    pending_version = state.get("pending_version")
    if pending_version and pending_version.get("content"):
        patch["pending_version"] = {**pending_version, "content": sanitize_chinese(pending_version["content"])}

    return patch
