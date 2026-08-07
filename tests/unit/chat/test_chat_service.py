import uuid
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from sqlalchemy.exc import SQLAlchemyError

import app.services.chat_service as chat_service_module
from app.models.manuscript import ConceptType
from app.services.chat_service import (
    DOCUMENT_GENERATION_ACK,
    ChatService,
    is_document_generation,
)
from app.utils.sse import SseEvent

pytestmark = pytest.mark.unit


@pytest.fixture(autouse=True)
def _stub_chat_model_key_for_manuscript(monkeypatch):
    """스트림/턴 단위 테스트는 DB 설정 조회 없이 registry key만 고정한다."""
    monkeypatch.setattr(
        chat_service_module,
        "chat_model_key_for_manuscript",
        lambda *_args, **_kwargs: "default",
    )


class FakeGraphRunner:
    def __init__(self, tokens=()):
        self._tokens = tokens
        self.updated_evidence_text = []

    async def stream_reply_tokens(self, manuscript_id, model):
        for token in self._tokens:
            yield token

    async def run_document_generation(self, manuscript_id, model):
        return None

    async def update_evidence_text(self, manuscript_id, model, evidence_text):
        self.updated_evidence_text.append(evidence_text)


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
    assert is_document_generation("generate_document") is True
    assert is_document_generation("outline") is True
    assert is_document_generation("say") is False
    assert is_document_generation(None) is False


async def test_stream_response_dispatches_document_generation():
    background = RecordingBackgroundTasks()
    service = _service(FakeGraphRunner(), background)

    events = [event async for event in service.stream_response(uuid.uuid4(), "generate_document")]

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


async def test_stream_response_withholds_reply_while_research_required():
    background = RecordingBackgroundTasks()
    service = _service(FakeGraphRunner(tokens=["절대", "안 나와야 함"]), background)

    events = [
        event
        async for event in service.stream_response(
            uuid.uuid4(), "say", research_required=True
        )
    ]

    assert events == [
        (SseEvent.READY, {}),
        (SseEvent.DONE, {"awaiting_research": True}),
    ]


async def test_begin_turn_skips_research_for_non_enabled_concepts(monkeypatch):
    message_id = uuid.uuid4()
    routed = {}

    class FakeRunner:
        async def route_turn(self, **kwargs):
            routed.update(kwargs)
            return {"user_action": "say"}

    class Session:
        def get(self, *_args):
            return SimpleNamespace(id=uuid.uuid4())

        def commit(self):
            return None

    monkeypatch.setattr(
        chat_service_module.chat_repo,
        "create_message",
        lambda *args, **kwargs: SimpleNamespace(id=message_id),
    )
    monkeypatch.setattr(
        chat_service_module,
        "detect_evidence_need",
        lambda _text: SimpleNamespace(
            required=True,
            claim_or_query="보통 CPU 점유율을 봅니다.",
        ),
    )
    service = ChatService(
        graph_runner=FakeRunner(),
        db_factory=_NullSession,
        background_tasks=RecordingBackgroundTasks(),
    )
    manuscript = SimpleNamespace(
        id=uuid.uuid4(),
        user_id=uuid.uuid4(),
        concept=ConceptType.TIL,
    )

    turn = await service.begin_turn(
        Session(),
        manuscript,
        "보통 CPU 점유율을 봅니다.",
    )

    assert turn.research_required is False
    assert turn.claim_or_query is None
    assert routed.get("evidence_text") is None


async def test_begin_turn_keeps_research_for_deepdive(monkeypatch):
    message_id = uuid.uuid4()
    routed = {}

    class FakeRunner:
        async def route_turn(self, **kwargs):
            routed.update(kwargs)
            return {"user_action": "say"}

    class Session:
        def get(self, *_args):
            return SimpleNamespace(id=uuid.uuid4())

        def commit(self):
            return None

    monkeypatch.setattr(
        chat_service_module.chat_repo,
        "create_message",
        lambda *args, **kwargs: SimpleNamespace(id=message_id),
    )
    monkeypatch.setattr(
        chat_service_module,
        "detect_evidence_need",
        lambda _text: SimpleNamespace(
            required=True,
            claim_or_query="보통 CPU 점유율을 봅니다.",
        ),
    )
    monkeypatch.setattr(
        "app.research.turn_evidence.load_evidence_text_for_turn",
        lambda **_kwargs: "검색된 근거 텍스트",
    )
    monkeypatch.setattr(
        "app.research.turn_evidence.evidence_sufficient_for_turn",
        lambda **_kwargs: False,
    )
    service = ChatService(
        graph_runner=FakeRunner(),
        db_factory=_NullSession,
        background_tasks=RecordingBackgroundTasks(),
    )
    manuscript = SimpleNamespace(
        id=uuid.uuid4(),
        user_id=uuid.uuid4(),
        concept=ConceptType.TECH_DEEPDIVE,
    )

    turn = await service.begin_turn(
        Session(),
        manuscript,
        "보통 CPU 점유율을 봅니다.",
    )

    assert turn.research_required is True
    assert turn.claim_or_query == "보통 CPU 점유율을 봅니다."
    assert routed["evidence_text"] == "검색된 근거 텍스트"


async def test_begin_turn_skips_research_when_already_sufficient(monkeypatch):
    """관련 URL이 이미 3개 이상이면 조사 플래그를 세우지 않는다."""
    message_id = uuid.uuid4()

    class FakeRunner:
        async def route_turn(self, **kwargs):
            return {"user_action": "say"}

    class Session:
        def get(self, *_args):
            return SimpleNamespace(id=uuid.uuid4())

        def commit(self):
            return None

    monkeypatch.setattr(
        chat_service_module.chat_repo,
        "create_message",
        lambda *args, **kwargs: SimpleNamespace(id=message_id),
    )
    monkeypatch.setattr(
        chat_service_module,
        "detect_evidence_need",
        lambda _text: SimpleNamespace(required=True, claim_or_query="보통 CPU 점유율을 봅니다."),
    )
    monkeypatch.setattr(
        "app.research.turn_evidence.load_evidence_text_for_turn",
        lambda **_kwargs: "검색된 근거 텍스트",
    )
    monkeypatch.setattr(
        "app.research.turn_evidence.evidence_sufficient_for_turn",
        lambda **_kwargs: True,
    )
    service = ChatService(
        graph_runner=FakeRunner(),
        db_factory=_NullSession,
        background_tasks=RecordingBackgroundTasks(),
    )
    manuscript = SimpleNamespace(
        id=uuid.uuid4(), user_id=uuid.uuid4(), concept=ConceptType.TECH_DEEPDIVE
    )

    turn = await service.begin_turn(Session(), manuscript, "보통 CPU 점유율을 봅니다.")

    assert turn.research_required is False
    assert turn.claim_or_query is None


@pytest.mark.parametrize("action", ["feedback", "refuse", "opening"])
async def test_begin_turn_skips_research_for_non_claim_actions(monkeypatch, action):
    """feedback/refuse/opening 턴은 조사 대상 주장 턴이 아니라서 조사를 걸지 않는다."""
    message_id = uuid.uuid4()
    sufficiency_calls = []

    class FakeRunner:
        async def route_turn(self, **kwargs):
            return {"user_action": action}

    class Session:
        def get(self, *_args):
            return SimpleNamespace(id=uuid.uuid4())

        def commit(self):
            return None

    monkeypatch.setattr(
        chat_service_module.chat_repo,
        "create_message",
        lambda *args, **kwargs: SimpleNamespace(id=message_id),
    )
    monkeypatch.setattr(
        chat_service_module,
        "detect_evidence_need",
        lambda _text: SimpleNamespace(required=True, claim_or_query=_text),
    )
    monkeypatch.setattr(
        "app.research.turn_evidence.load_evidence_text_for_turn",
        lambda **_kwargs: "",
    )

    def _record_sufficiency_call(**kwargs):
        sufficiency_calls.append(kwargs)
        return False

    monkeypatch.setattr(
        "app.research.turn_evidence.evidence_sufficient_for_turn",
        _record_sufficiency_call,
    )
    service = ChatService(
        graph_runner=FakeRunner(),
        db_factory=_NullSession,
        background_tasks=RecordingBackgroundTasks(),
    )
    manuscript = SimpleNamespace(
        id=uuid.uuid4(), user_id=uuid.uuid4(), concept=ConceptType.TECH_DEEPDIVE
    )

    turn = await service.begin_turn(Session(), manuscript, "보통 CPU 점유율을 봅니다.")

    assert turn.research_required is False
    assert turn.claim_or_query is None
    assert sufficiency_calls == []


async def test_stream_grounded_reply_after_research_updates_evidence_and_streams(
    monkeypatch,
):
    background = RecordingBackgroundTasks()
    graph_runner = FakeGraphRunner(tokens=["근거", "반영 답변"])
    service = _service(graph_runner, background)
    manuscript = SimpleNamespace(id=uuid.uuid4(), user_id=uuid.uuid4())
    job = SimpleNamespace(claim_or_query="보통 CPU 점유율을 봅니다.")

    monkeypatch.setattr(
        "app.research.turn_evidence.load_evidence_text_for_turn",
        lambda **_kwargs: "새로 조사한 근거",
    )

    events = [
        event
        async for event in service.stream_grounded_reply_after_research(
            manuscript, job
        )
    ]

    assert events[0] == (SseEvent.READY, {})
    chunks = [payload["content"] for name, payload in events if name == SseEvent.CHUNK]
    assert "".join(chunks) == "근거반영 답변"
    assert events[-1] == (SseEvent.DONE, {})
    assert graph_runner.updated_evidence_text == ["새로 조사한 근거"]


def test_save_chat_message_propagates_db_error(monkeypatch):
    def boom(*args, **kwargs):
        raise SQLAlchemyError("db down")

    monkeypatch.setattr(chat_service_module.chat_repo, "create_message", boom)
    session = MagicMock()
    manuscript = SimpleNamespace(id=uuid.uuid4())

    with pytest.raises(SQLAlchemyError, match="db down"):
        ChatService._save_chat_message(
            session, manuscript, "user", "내용", None
        )
