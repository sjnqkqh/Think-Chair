"""DeepSeek(chat/completions) 호출 목적 로깅.

httpx의 URL만으로는 어느 단계 호출인지 구분되지 않아, purpose를 남긴다.
"""

from __future__ import annotations

from typing import Any

from langchain_core.callbacks import BaseCallbackHandler

from app.logging import get_logger

logger = get_logger(__name__)


def log_deepseek_request(*, purpose: str, **fields: Any) -> None:
    logger.info("llm.deepseek.request", purpose=purpose, **fields)


def log_deepseek_response(*, purpose: str, **fields: Any) -> None:
    logger.info("llm.deepseek.response", purpose=purpose, **fields)


def _purpose_from_metadata(metadata: dict[str, Any] | None) -> str:
    if not metadata:
        return "chat.unknown"
    node = metadata.get("langgraph_node")
    if isinstance(node, str) and node.strip():
        return f"chat.{node.strip()}"
    return "chat.unknown"


class DeepSeekGraphCallLogger(BaseCallbackHandler):
    """LangGraph 노드에서 ChatOpenAI가 돌 때 langgraph_node로 purpose를 남긴다."""

    def on_chat_model_start(
        self,
        serialized: dict[str, Any],
        messages: list,
        *,
        run_id,
        metadata: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> None:
        purpose = _purpose_from_metadata(metadata)
        log_deepseek_request(
            purpose=purpose,
            message_count=len(messages),
            run_id=str(run_id),
        )

    def on_chat_model_end(
        self,
        response,
        *,
        run_id,
        metadata: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> None:
        purpose = _purpose_from_metadata(metadata)
        generations = getattr(response, "generations", None) or []
        text_len = 0
        if generations and generations[0]:
            first = generations[0][0]
            text = getattr(getattr(first, "message", None), "content", None) or getattr(
                first, "text", ""
            )
            text_len = len(str(text or ""))
        log_deepseek_response(
            purpose=purpose,
            response_chars=text_len,
            run_id=str(run_id),
        )
