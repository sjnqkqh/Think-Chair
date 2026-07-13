from langchain_core.messages import AIMessage, SystemMessage
from langchain_core.runnables import RunnableConfig

from app.graph.llm_registry import get as get_llm
from app.graph.prompts import build_system_prompt
from app.graph.prompts.phases.polish import POLISH_FINAL_GUARD
from app.graph.state import GraphState


async def polish_node(state: GraphState, config: RunnableConfig) -> dict:
    llm = get_llm(config["configurable"].get("model", "default"))
    system = build_system_prompt(
        state["concept"],
        phase="polish",
        topic=state["topic"],
        user_nickname=state.get("user_nickname"),
        audience=state.get("audience_level"),
    )

    resp = await llm.ainvoke(
        [
            SystemMessage(content=system),
            *state["messages"],
            SystemMessage(content=POLISH_FINAL_GUARD.text),
        ]
    )
    return {
        "messages": [AIMessage(content="작성 완료되었습니다. 내용 확인 후 수정 필요하시면 말씀해주세요.")],
        "new_paper": {"kind": "polish", "content": resp.content},
    }
