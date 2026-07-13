from langchain_core.messages import SystemMessage
from langchain_core.runnables import RunnableConfig

from app.graph.llm_registry import get as get_language_model
from app.graph.prompts import build_system_prompt
from app.graph.prompts.phases.outline import OUTLINE_FINAL_GUARD
from app.graph.state import GraphState


async def outline_node(state: GraphState, config: RunnableConfig) -> dict:
    configuration = config
    language_model = get_language_model(
        configuration["configurable"].get("model", "default")
    )
    system = build_system_prompt(
        state["concept"],
        phase="outline",
        topic=state["topic"],
        user_nickname=state.get("user_nickname"),
        audience=state.get("audience_level"),
    )
    response = await language_model.ainvoke(
        [
            SystemMessage(content=system),
            *state["messages"],
            SystemMessage(content=OUTLINE_FINAL_GUARD.text),
        ]
    )
    return {
        "client_message": "개요 작성 완료되었습니다. 확인해보세요.",
        "new_paper": {"kind": "outline", "content": response.content},
    }
