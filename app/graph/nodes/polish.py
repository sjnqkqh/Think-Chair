from langchain_core.messages import SystemMessage
from langchain_core.runnables import RunnableConfig

from app.graph.llm_registry import get as get_language_model
from app.graph.prompts import build_system_prompt
from app.graph.prompts.phases.polish import POLISH_FINAL_GUARD
from app.graph.state import GraphState


async def polish_node(state: GraphState, config: RunnableConfig) -> dict:
    configuration = config
    language_model = get_language_model(
        configuration["configurable"].get("model", "default")
    )
    system = build_system_prompt(
        state["concept"],
        phase="polish",
        topic=state["topic"],
        user_nickname=state.get("user_nickname"),
        audience=state.get("audience_level"),
    )

    response = await language_model.ainvoke(
        [
            SystemMessage(content=system),
            *state["messages"],
            SystemMessage(content=POLISH_FINAL_GUARD.text),
        ]
    )
    return {
        "client_message": "작성 완료되었습니다. 내용 확인 후 수정 필요하시면 말씀해주세요.",
        "new_paper": {"kind": "polish", "content": response.content},
    }
