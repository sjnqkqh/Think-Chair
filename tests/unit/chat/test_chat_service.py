import uuid
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from sqlalchemy.exc import SQLAlchemyError

import app.services.chat_service as chat_service_module
from app.services.chat_service import (
    DOCUMENT_GENERATION_ACK,
    ChatService,
    is_document_generation,
)
from app.utils.sse import SseEvent

pytestmark = pytest.mark.unit


class FakeGraphRunner:
    def __init__(self, tokens=()):
        self._tokens = tokens

    async def stream_reply_tokens(self, manuscript_id, model):
        for token in self._tokens:
            yield token

    async def run_document_generation(self, manuscript_id, model):
        return None


class RecordingBackgroundTasks:
    def __init__(self):
        self.started = []

    def start(self, coroutine):
        self.started.append(coroutine)
        coroutine.close()  # 실제 실행 없이 "never awaited" 경고만 방지


class _NullSession:
    """save 경로를 타지 않도록 manuscript를 못 찾는 세션."""

    def get(self, *args):
        return None

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def _service(graph_runner, background_tasks):
    return ChatService(
        graph_runner=graph_runner,
        db_factory=_NullSession,
        background_tasks=background_tasks,
    )


def test_is_document_generation_predicate():
    assert is_document_generation("polish") is True
    assert is_document_generation("outline") is True
    assert is_document_generation("say") is False
    assert is_document_generation(None) is False


async def test_stream_response_dispatches_document_generation():
    background = RecordingBackgroundTasks()
    service = _service(FakeGraphRunner(), background)

    events = [event async for event in service.stream_response(uuid.uuid4(), "polish")]

    assert events[0] == (SseEvent.READY, {})
    assert (SseEvent.CHUNK, {"content": DOCUMENT_GENERATION_ACK}) in events
    assert events[-1] == (SseEvent.DONE, {"document_generation": True})
    assert len(background.started) == 1


async def test_stream_response_dispatches_assistant_reply():
    background = RecordingBackgroundTasks()
    service = _service(FakeGraphRunner(tokens=["안녕", "하세요"]), background)

    events = [event async for event in service.stream_response(uuid.uuid4(), "say")]

    assert events[0] == (SseEvent.READY, {})
    chunks = [payload["content"] for name, payload in events if name == SseEvent.CHUNK]
    assert "".join(chunks) == "안녕하세요"
    assert events[-1] == (SseEvent.DONE, {})
    assert background.started == []


def test_save_chat_message_returns_in_memory_on_db_error(monkeypatch, caplog):
    # 저장 실패 시 예외를 삼키고 rollback + 로깅 후 in-memory 메시지를 돌려줘야 한다.
    def boom(*args, **kwargs):
        raise SQLAlchemyError("db down")

    monkeypatch.setattr(chat_service_module.chat_repo, "create_message", boom)
    session = MagicMock()
    manuscript = SimpleNamespace(id=uuid.uuid4())

    with caplog.at_level("ERROR", logger="app.services.chat_service"):
        message = ChatService._save_chat_message(
            session, manuscript, "user", "내용", None
        )

    assert message.content == "내용"
    assert message.sequence == 1
    session.rollback.assert_called_once()
    assert any("채팅 기록 저장 실패" in record.message for record in caplog.records)
