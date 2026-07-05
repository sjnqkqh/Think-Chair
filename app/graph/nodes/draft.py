from langchain_core.messages import AIMessage, SystemMessage
from langchain_core.runnables import RunnableConfig

from app.graph.llm_registry import get as get_llm
from app.graph.prompts import build_system_prompt
from app.graph.state import DraftsmithState


async def draft_node(state: DraftsmithState, config: RunnableConfig) -> dict:
    llm = get_llm(config["configurable"].get("model", "default"))
    system = build_system_prompt(
        state["concept"],
        phase="draft",
        topic=state["topic"],
        audience=state.get("audience_level"),
    )
    resp = await llm.ainvoke([SystemMessage(content=system), *state["messages"]])
    # converse_node와 달리 pending_version을 채운다 -> builder.py의 조건부 엣지가
    # chinese_prevent 이후 persist_version으로 이어지게 만드는 트리거가 된다.
    return {
        "messages": [AIMessage(content="초고 작성 완료되었습니다. 확인해보세요.")],
        "pending_version": {"kind": "draft", "content": resp.content},
    }
