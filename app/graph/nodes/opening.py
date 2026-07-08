from langchain_core.messages import AIMessage, SystemMessage
from langchain_core.runnables import RunnableConfig

from app.graph.llm_registry import get as get_language_model
from app.graph.prompts import build_system_prompt
from app.graph.state import DraftsmithState


async def opening_node(state: DraftsmithState, config: RunnableConfig) -> dict:
    configuration = config
    language_model = get_language_model(
        configuration["configurable"].get("model", "default")
    )
    system = build_system_prompt(
        state["concept"],
        phase="opening",
        topic=state["topic"],
        user_nickname=state.get("user_nickname"),
        audience=state.get("audience_level"),
    )
    response = await language_model.ainvoke(
        [
            SystemMessage(content=system),
            *state["messages"],
        ]
    )
    return {"messages": [AIMessage(content=response.content)]}
