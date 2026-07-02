from langchain_core.messages import AIMessage, SystemMessage
from langchain_core.runnables import RunnableConfig

from app.graph.llm_registry import get as get_llm
from app.graph.prompts import build_system_prompt
from app.graph.state import DraftsmithState


async def outline_node(state: DraftsmithState, config: RunnableConfig) -> dict:
    llm = get_llm(config["configurable"].get("model", "default"))
    system = build_system_prompt(
        state["concept"],
        phase="outline",
        topic=state["topic"],
        audience=state.get("audience_level"),
    )
    resp = await llm.ainvoke([SystemMessage(content=system), *state["messages"]])
    return {
        "messages": [AIMessage(content=resp.content)],
        "pending_version": {"kind": "outline", "content": resp.content},
    }
