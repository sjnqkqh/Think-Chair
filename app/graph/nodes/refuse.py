from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langchain_core.runnables import RunnableConfig

from app.graph.llm_registry import get as get_language_model
from app.graph.prompts.phases.document_readiness import INSUFFICIENT_CONTEXT_RESPONSE
from app.graph.state import GraphState
from app.graph.transcript import render_transcript


async def refuse_node(state: GraphState, config: RunnableConfig) -> dict:
    language_model = get_language_model(config["configurable"].get("model", "default"))
    transcript = render_transcript(state["messages"])
    response = await language_model.ainvoke(
        [
            SystemMessage(content=INSUFFICIENT_CONTEXT_RESPONSE.text),
            HumanMessage(
                content=(
                    f"[대화 내역]\n{transcript}\n\n"
                    "위 대화를 참고해, 규칙에 따라 문서 작성을 거절하고 "
                    "필요한 정보를 요청하십시오."
                )
            ),
        ]
    )
    return {
        "messages": [AIMessage(content=response.content)],
        "client_message": response.content,
    }
