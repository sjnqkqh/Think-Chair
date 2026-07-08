import logging
import uuid

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langchain_core.runnables import RunnableConfig

from app.graph.llm_registry import get as get_language_model
from app.graph.prompts.classifier import CLASSIFIER
from app.graph.state import DraftsmithState
from app.models.chat import RoutingDecision

logger = logging.getLogger(__name__)

CLASSIFIABLE_ACTIONS = {"say", "feedback", "outline", "polish"}


def _last_human_message(state: DraftsmithState) -> HumanMessage | None:
    return next(
        (
            message
            for message in reversed(state["messages"])
            if isinstance(message, HumanMessage)
        ),
        None,
    )


def _is_opening_turn(state: DraftsmithState) -> bool:
    human_messages = [
        message for message in state["messages"] if isinstance(message, HumanMessage)
    ]
    return len(human_messages) == 1 and not any(
        isinstance(message, AIMessage) for message in state["messages"]
    )


def _message_preview(message: HumanMessage | None) -> str:
    if message is None or not message.content:
        return ""
    return str(message.content)[:30]


async def _classify_human_message(
    human_message: HumanMessage, configuration: RunnableConfig
) -> str:
    language_model = get_language_model(
        configuration["configurable"].get("model", "default")
    )
    response = await language_model.ainvoke(
        [SystemMessage(content=CLASSIFIER.text), human_message]
    )
    return (response.content or "").strip()


def _parse_classification(
    classification_text: str, message_preview: str
) -> tuple[str, str]:
    action_text, _, reason_text = classification_text.partition("|")
    action = action_text.strip().lower()
    reason = reason_text.strip()

    if action in CLASSIFIABLE_ACTIONS:
        return action, reason

    logger.warning(
        "router_node: message=%r unrecognized classification %r, falling back to 'say'",
        message_preview,
        classification_text,
    )
    return "say", "분류 실패로 기본값 적용"


def _record_routing_decision(
    state: DraftsmithState,
    config: RunnableConfig,
    decision: str,
    reason: str,
    raw_output: str | None,
) -> None:
    db = config["configurable"].get("db_session")
    if db is None:
        return

    message_id = state.get("current_message_id")
    db.add(
        RoutingDecision(
            manuscript_id=uuid.UUID(state["manuscript_id"]),
            message_id=uuid.UUID(message_id) if message_id else None,
            router_name="intent",
            decision=decision,
            reason=reason,
            raw_output=raw_output,
        )
    )


async def router_node(state: DraftsmithState, config: RunnableConfig) -> dict:
    configuration = config
    last_human_message = _last_human_message(state)
    message_preview = _message_preview(last_human_message)

    if last_human_message is None or not last_human_message.content:
        logger.info(
            "router_node: message=%r -> action=say reason=빈 메시지",
            message_preview,
        )
        _record_routing_decision(state, configuration, "say", "빈 메시지", None)
        return {"user_action": "say"}

    if _is_opening_turn(state):
        logger.info(
            "router_node: message=%r -> action=opening reason=첫 대화 시작",
            message_preview,
        )
        _record_routing_decision(state, configuration, "opening", "첫 대화 시작", None)
        return {"user_action": "opening"}

    classification_text = await _classify_human_message(
        last_human_message, configuration
    )
    action, reason = _parse_classification(classification_text, message_preview)

    logger.info(
        "router_node: message=%r -> action=%s reason=%s",
        message_preview,
        action,
        reason,
    )

    _record_routing_decision(state, configuration, action, reason, classification_text)
    return {"user_action": action}


def route_by_action(state: DraftsmithState) -> str:
    return state.get("user_action") or "say"
