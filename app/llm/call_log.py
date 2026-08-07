"""채팅 LLM(chat/completions) 호출 목적 로깅.

httpx의 URL만으로는 어느 단계 호출인지 구분되지 않아, purpose와 model을 남긴다.
"""

from __future__ import annotations

from typing import Any

from langchain_core.callbacks import BaseCallbackHandler

from app.logging import get_logger

logger = get_logger(__name__)


def _purpose_from_metadata(metadata: dict[str, Any] | None) -> str:
    if not metadata:
        return "chat.unknown"
    node = metadata.get("langgraph_node")
    if isinstance(node, str) and node.strip():
        return f"chat.{node.strip()}"
    return "chat.unknown"


def _model_from_call(
    *,
    metadata: dict[str, Any] | None,
    kwargs: dict[str, Any],
) -> str | None:
    if metadata:
        for key in ("ls_model_name", "model_name", "model"):
            value = metadata.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
    invocation = kwargs.get("invocation_params") or {}
    if isinstance(invocation, dict):
        for key in ("model", "model_name"):
            value = invocation.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
    return None


class ChatModelCallLogger(BaseCallbackHandler):
    """LangGraph 노드에서 채팅 LLM이 돌 때 purpose·model을 남긴다."""

    def on_chat_model_start(
        self,
        serialized: dict[str, Any],
        messages: list,
        *,
        run_id,
        metadata: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> None:
        logger.info(
            "llm.chat.request",
            purpose=_purpose_from_metadata(metadata),
            model=_model_from_call(metadata=metadata, kwargs=kwargs),
            message_count=len(messages),
            run_id=str(run_id),
        )
