from langchain_core.messages import SystemMessage
from langchain_core.runnables import RunnableConfig

from app.graph.llm_registry import get as get_language_model
from app.graph.prompts import build_system_prompt
from app.graph.prompts.phases.polish import POLISH_FINAL_GUARD, POLISH_STEP_BACK
from app.graph.state import GraphState


async def polish_node(state: GraphState, config: RunnableConfig) -> dict:
    configuration = config
    language_model = get_language_model(
        configuration["configurable"].get("model", "default")
    )
    attempts = state.get("polish_attempts", 0)

    system = build_system_prompt(
        state["concept"],
        phase="polish",
        topic=state["topic"],
        user_nickname=state.get("user_nickname"),
        audience=state.get("audience_level"),
    )

    prompt_messages = [
        SystemMessage(content=system),
        *state["messages"],
        SystemMessage(content=POLISH_FINAL_GUARD.text),
    ]
    if attempts >= 1:
        prompt_messages.append(SystemMessage(content=POLISH_STEP_BACK.text))

    response = await language_model.ainvoke(prompt_messages)
    return {
        "client_message": "작성 완료되었습니다. 내용 확인 후 수정 필요하시면 말씀해주세요.",
        "new_paper": {"kind": "polish", "content": response.content},
        "polish_attempts": attempts + 1,
    }
