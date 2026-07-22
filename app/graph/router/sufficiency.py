from langchain_core.messages import HumanMessage, SystemMessage
from langchain_core.runnables import RunnableConfig

from app.logging import get_logger
from app.graph.llm_registry import get as get_language_model
from app.graph.prompts.phases.document_readiness import DOCUMENT_READINESS_CHECK
from app.graph.state import GraphState
from app.graph.transcript import render_transcript
from app.services.sufficiency_response_parser import parse_sufficiency_response

logger = get_logger(__name__)

MIN_HUMAN_MESSAGES = 2
MIN_USER_CHARS = 120
MAX_GATE_ATTEMPTS = 3


def _human_messages(state: GraphState) -> list[HumanMessage]:
    return [m for m in state["messages"] if isinstance(m, HumanMessage)]


def _passes_heuristic(state: GraphState) -> bool:
    human_messages = _human_messages(state)
    total_chars = sum(len(str(m.content or "")) for m in human_messages)
    return len(human_messages) >= MIN_HUMAN_MESSAGES and total_chars >= MIN_USER_CHARS


async def is_conversation_sufficient(
    state: GraphState, config: RunnableConfig
) -> tuple[bool, str, str | None, str]:
    """(충분여부, 사유, LLM raw_output, 판정 소스).

    판정 소스는 "heuristic"(휴리스틱 미달로 LLM 없이 거절), "llm"(정상 판정),
    "llm-retry-exhausted"(재시도 소진) 중 하나. 휴리스틱 통과 시에만 LLM을 호출한다.

    대화를 라이브 채팅 턴으로 재생하지 않고 참조 텍스트로 임베드한다. 그렇지 않으면
    마지막 '문서 작성' 요청에 모델이 순응해 판정 대신 문서를 생성한다.
    게이트가 JSON 형식을 어기면 최대 MAX_GATE_ATTEMPTS회 재시도한다.
    """
    if not _passes_heuristic(state):
        return False, "대화량이 문서 작성 기준에 미달", None, "heuristic"

    language_model = get_language_model(config["configurable"].get("model", "default"))
    transcript = render_transcript(state["messages"])
    prompt = [
        SystemMessage(content=DOCUMENT_READINESS_CHECK.text),
        HumanMessage(
            content=(
                f"[대화 내역]\n{transcript}\n\n"
                "위 대화만으로 요청된 문서를 작성할 근거가 충분한지 "
                "지정된 JSON 형식으로만 판정하십시오."
            )
        ),
    ]

    last_raw: str | None = None
    for attempt in range(1, MAX_GATE_ATTEMPTS + 1):
        response = await language_model.ainvoke(prompt)
        last_raw = (response.content or "").strip()
        decision = parse_sufficiency_response(last_raw)
        if decision is not None:
            logger.info(
                "document_readiness.decision", attempt=attempt, decision=decision
            )
            return (
                decision.sufficient,
                decision.reason
                or ("대화 맥락 충분" if decision.sufficient else "대화 맥락 불충분"),
                last_raw,
                "llm",
            )
        logger.warning(
            "document_readiness.invalid", attempt=attempt, raw_output=last_raw[:200]
        )

    logger.error(
        "document_readiness.retry_exhausted", raw_output=(last_raw or "")[:200]
    )
    return (
        True,
        "게이트 판정 실패(재시도 소진) - 생성으로 진행",
        last_raw,
        "llm-retry-exhausted",
    )
