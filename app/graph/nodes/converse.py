from langchain_core.messages import AIMessage, SystemMessage
from langchain_core.runnables import RunnableConfig

from app.graph.llm_registry import get as get_language_model
from app.graph.prompts import build_system_prompt
from app.graph.prompts.phases.say import SAY_DOCUMENT_GUARD
from app.graph.state import GraphState


async def converse_node(state: GraphState, config: RunnableConfig) -> dict:
    configuration = config
    language_model = get_language_model(
        configuration["configurable"].get("model", "default")
    )
    system = build_system_prompt(
        state["concept"],
        phase=state["user_action"],
        topic=state["topic"],
        user_nickname=state.get("user_nickname"),
        audience=state.get("audience_level"),
    )
    response = await language_model.ainvoke(
        [
            SystemMessage(content=system),
            *state["messages"],
            SystemMessage(content=SAY_DOCUMENT_GUARD.text),
        ]
    )
    return {
        "messages": [AIMessage(content=response.content)],
        "client_message": response.content,
    }
