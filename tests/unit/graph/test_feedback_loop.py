from unittest.mock import MagicMock

import pytest
from langchain_core.language_models.fake_chat_models import FakeListChatModel
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

from app.graph import llm_registry as language_model_registry
from app.graph.nodes.evaluate import evaluate_polish_node
from app.graph.nodes.polish import polish_node
from app.graph.prompts.phases.polish import POLISH_STEP_BACK
from app.graph.router.intent_router import router_node
from app.graph.router.sufficiency import _passes_heuristic
from app.graph.transcript import render_transcript

pytestmark = pytest.mark.unit

_MANUSCRIPT_ID = "11111111-1111-1111-1111-111111111111"
_VERSION_ID = "22222222-2222-2222-2222-222222222222"


def _base_state(**overrides):
    state = {
        "manuscript_id": _MANUSCRIPT_ID,
        "concept": "딥다이브",
        "topic": "테스트 주제",
        "user_nickname": "테스터",
        "audience_level": None,
        "user_action": "polish",
        "current_message_id": None,
        "messages": [HumanMessage(content="원고를 작성해줘")],
        "client_message": None,
        "new_paper": None,
        "polish_attempts": 0,
    }
    state.update(overrides)
    return state


class _RegisteredModel:
    def __init__(self, model):
        self._model = model
        self._original = language_model_registry._registry.get("default")

    def __enter__(self):
        language_model_registry.register("default", self._model)
        return self._model

    def __exit__(self, *exc):
        if self._original is not None:
            language_model_registry.register("default", self._original)


def _rich_messages():
    return [
        HumanMessage(content="어텐션 메커니즘을 백엔드 개발자 대상으로 설명하고 싶어. " * 3),
        AIMessage(content="이 주제에서 어디까지 이해하고 있나요?"),
        HumanMessage(content="RNN은 알지만 트랜스포머는 처음인 사람들이야. 코드보다 직관 위주로." * 3),
    ]


# --- Feature 1: 충분성 게이트 ---


def test_heuristic_rejects_short_conversation():
    assert _passes_heuristic(_base_state()) is False


def test_heuristic_accepts_rich_conversation():
    assert _passes_heuristic(_base_state(messages=_rich_messages())) is True


def test_render_transcript_labels_roles_and_skips_empty():
    rendered = render_transcript(
        [
            HumanMessage(content="첫 질문"),
            AIMessage(content=""),
            AIMessage(content="답변"),
        ]
    )
    assert rendered == "사용자: 첫 질문\nAI: 답변"


@pytest.mark.asyncio
async def test_router_refuses_when_heuristic_fails_without_gate_llm():
    # classifier만 호출되고(휴리스틱 미달) 게이트 LLM은 호출되지 않아야 한다.
    with _RegisteredModel(FakeListChatModel(responses=["polish"])):
        state = _base_state(
            user_action=None,
            messages=[
                HumanMessage(content="안녕하세요"),
                AIMessage(content="무엇을 도와드릴까요?"),
                HumanMessage(content="문서 작성해줘"),
            ],
        )
        result = await router_node(state, {"configurable": {"model": "default"}})
        assert result["user_action"] == "refuse"


@pytest.mark.asyncio
async def test_router_keeps_action_when_gate_llm_says_sufficient():
    with _RegisteredModel(
        FakeListChatModel(
            responses=["polish", '{"sufficient": true, "reason": "근거 충분"}']
        )
    ):
        state = _base_state(user_action=None, messages=_rich_messages())
        result = await router_node(state, {"configurable": {"model": "default"}})
        assert result["user_action"] == "polish"


@pytest.mark.asyncio
async def test_router_refuses_when_gate_llm_says_insufficient():
    with _RegisteredModel(
        FakeListChatModel(
            responses=["polish", '{"sufficient": false, "reason": "방향성 부족"}']
        )
    ):
        state = _base_state(user_action=None, messages=_rich_messages())
        result = await router_node(state, {"configurable": {"model": "default"}})
        assert result["user_action"] == "refuse"


@pytest.mark.asyncio
async def test_router_retries_gate_until_valid_json():
    # 첫 응답이 형식 위반이면 재시도해 유효한 JSON 판정을 신뢰한다.
    with _RegisteredModel(
        FakeListChatModel(
            responses=[
                "polish",
                "# 문서를 생성해버림",
                '{"sufficient": false, "reason": "방향성 부족"}',
            ]
        )
    ):
        state = _base_state(user_action=None, messages=_rich_messages())
        result = await router_node(state, {"configurable": {"model": "default"}})
        assert result["user_action"] == "refuse"


@pytest.mark.asyncio
async def test_router_proceeds_when_gate_retries_exhausted():
    # 재시도를 모두 소진하면(계속 형식 위반) 생성으로 진행한다(오거절 방지).
    with _RegisteredModel(
        FakeListChatModel(responses=["polish", "# 계속 문서만 생성"])
    ):
        state = _base_state(user_action=None, messages=_rich_messages())
        result = await router_node(state, {"configurable": {"model": "default"}})
        assert result["user_action"] == "polish"


# --- Feature 2-1: step-back 재시도 ---


class _RecordingModel:
    def __init__(self):
        self.messages = None

    async def ainvoke(self, messages):
        self.messages = messages
        return AIMessage(content="생성된 원고 본문")


@pytest.mark.asyncio
async def test_polish_node_injects_step_back_on_retry():
    with _RegisteredModel(_RecordingModel()) as model:
        state = _base_state(polish_attempts=1)
        result = await polish_node(state, {"configurable": {"model": "default"}})
        assert result["polish_attempts"] == 2
        assert model.messages[-1].content == POLISH_STEP_BACK.text


@pytest.mark.asyncio
async def test_polish_node_no_step_back_on_first_attempt():
    with _RegisteredModel(_RecordingModel()) as model:
        state = _base_state(polish_attempts=0)
        result = await polish_node(state, {"configurable": {"model": "default"}})
        assert result["polish_attempts"] == 1
        assert POLISH_STEP_BACK.text not in [
            m.content for m in model.messages if isinstance(m, SystemMessage)
        ]


# --- Feature 2-2: 체크리스트 평가 저장 ---

@pytest.mark.asyncio
async def test_evaluate_polish_node_persists_evaluation():
    db = MagicMock()
    raw = '''{
        "score": 70,
        "verdict": "보완 필요",
        "reason": "근거 부족",
        "improvements": ["수치 추가"],
        "has_unnecessary_header": true,
        "has_unnecessary_footer": false
    }'''
    with _RegisteredModel(FakeListChatModel(responses=[raw])):
        state = _base_state(
            new_paper={
                "kind": "polish",
                "content": "본문",
                "version_id": _VERSION_ID,
            }
        )
        result = await evaluate_polish_node(
            state, {"configurable": {"model": "default", "db_session": db}}
        )
    assert result == {}
    db.add.assert_called_once()
    saved = db.add.call_args[0][0]
    assert saved.score == 70
    assert saved.verdict == "보완 필요"
    assert saved.has_unnecessary_header is True
    assert saved.has_unnecessary_footer is False
    assert saved.checklist_id
    db.commit.assert_called_once()


@pytest.mark.asyncio
async def test_evaluate_polish_node_uses_db_factory_when_request_session_is_missing():
    database_session = MagicMock()
    db_factory = MagicMock()
    db_factory.return_value.__enter__.return_value = database_session
    with _RegisteredModel(FakeListChatModel(responses=['{"score": 70}'])):
        state = _base_state(
            new_paper={
                "kind": "polish",
                "content": "본문",
                "version_id": _VERSION_ID,
            }
        )
        await evaluate_polish_node(
            state, {"configurable": {"model": "default", "db_factory": db_factory}}
        )

    database_session.add.assert_called_once()
    database_session.commit.assert_called_once()


@pytest.mark.asyncio
async def test_evaluate_polish_node_skips_non_polish():
    db = MagicMock()
    state = _base_state(new_paper={"kind": "outline", "content": "개요", "version_id": _VERSION_ID})
    result = await evaluate_polish_node(
        state, {"configurable": {"model": "default", "db_session": db}}
    )
    assert result == {}
    db.add.assert_not_called()
