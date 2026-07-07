import logging

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_core.runnables import RunnableConfig

from app.graph.llm_registry import get as get_llm
from app.graph.prompts.classifier import CLASSIFIER
from app.graph.state import DraftsmithState

logger = logging.getLogger(__name__)

CLASSIFIABLE_ACTIONS = {"say", "feedback", "outline", "polish"}


async def router_node(state: DraftsmithState, config: RunnableConfig) -> dict:
    last_human = next(
        (m for m in reversed(state["messages"]) if isinstance(m, HumanMessage)), None
    )
    if last_human is None or not last_human.content:
        logger.info("router_node: msg=%r -> action=say reason=빈 메시지", "")
        return {"user_action": "say"}

    preview = str(last_human.content)[:30]

    llm = get_llm(config["configurable"].get("model", "default"))
    resp = await llm.ainvoke([SystemMessage(content=CLASSIFIER.text), last_human])
    raw = (resp.content or "").strip()
    action_part, _, reason_part = raw.partition("|")
    action = action_part.strip().lower()
    reason = reason_part.strip()

    if action not in CLASSIFIABLE_ACTIONS:
        logger.warning(
            "router_node: msg=%r unrecognized classification %r, falling back to 'say'", preview, raw
        )
        action = "say"
        reason = "분류 실패로 기본값 적용"

    logger.info("router_node: msg=%r -> action=%s reason=%s", preview, action, reason)

    return {"user_action": action}


def route_by_action(state: DraftsmithState) -> str:
    return state.get("user_action") or "say"
