from langchain_core.messages import SystemMessage
from langchain_core.runnables import RunnableConfig

from app.graph.llm_registry import get as get_language_model
from app.graph.prompts import build_system_prompt
from app.graph.prompts.phases.document_generation import (
    DOCUMENT_FINAL_GUARD,
    DOCUMENT_STEP_BACK,
)
from app.graph.state import GraphState


async def generate_document_from_conversation_node(
    state: GraphState, config: RunnableConfig
) -> dict:
    configuration = config
    language_model = get_language_model(
        configuration["configurable"].get("model", "default")
    )
    attempts = state.get("document_generation_attempts", 0)

    system = build_system_prompt(
        state["concept"],
        phase="generate_document",
        topic=state["topic"],
        user_nickname=state.get("user_nickname"),
        audience_level=state.get("audience_level"),
    )

    prompt_messages = [
        SystemMessage(content=system),
        *state["messages"],
        SystemMessage(content=DOCUMENT_FINAL_GUARD.text),
    ]
    if attempts >= 1:
        prompt_messages.append(SystemMessage(content=DOCUMENT_STEP_BACK.text))

    response = await language_model.ainvoke(prompt_messages)
    return {
        "client_message": "작성 완료되었습니다. 내용 확인 후 수정 필요하시면 말씀해주세요.",
        "new_paper": {"kind": "document", "content": response.content},
        "document_generation_attempts": attempts + 1,
    }
