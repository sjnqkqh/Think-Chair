from unittest.mock import MagicMock

import pytest
from langchain_core.language_models.fake_chat_models import FakeListChatModel
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

from app.graph import llm_registry as language_model_registry
from app.graph.nodes.chinese_prevent import chinese_prevent_node
from app.graph.nodes.opening import opening_node
from app.graph.nodes.outline import outline_node
from app.graph.nodes.persist_version import persist_version_node
from app.graph.nodes.polish import polish_node
from app.graph.nodes.router import router_node
from app.graph.prompts.phases.outline import OUTLINE_FINAL_GUARD
from app.graph.prompts.phases.polish import POLISH_FINAL_GUARD


def _base_state(**overrides):
    state = {
        "manuscript_id": "11111111-1111-1111-1111-111111111111",
        "concept": "TIL",
        "topic": "테스트 주제",
        "user_nickname": "테스터",
        "audience_level": None,
        "user_action": "polish",
        "messages": [HumanMessage(content="원고를 작성해줘")],
        "pending_version": None,
    }
    state.update(overrides)
    return state


class RecordingLanguageModel:
    def __init__(self):
        self.messages = None

    async def ainvoke(self, messages):
        self.messages = messages
        return AIMessage(content="생성된 원고 본문")


def test_chinese_prevent_node_removes_chinese_from_message_and_pending_version():
    state = _base_state(
        messages=[AIMessage(content="漢字テスト 결과", id="message-1")],
        pending_version={"kind": "polish", "content": "漢字テスト 본문"},
    )

    result = chinese_prevent_node(state)

    assert "漢字" not in result["messages"][0].content
    assert result["messages"][0].id == "message-1"
    assert "漢字" not in result["pending_version"]["content"]


def test_persist_version_node_saves_to_storage_and_db():
    storage = MagicMock()
    db = MagicMock()
    db.query.return_value.filter.return_value.order_by.return_value.first.return_value = None

    state = _base_state(pending_version={"kind": "polish", "content": "저장할 본문"})
    config = {"configurable": {"storage": storage, "db_session": db}}

    result = persist_version_node(state, config)

    storage.save.assert_called_once()
    saved_key, saved_bytes = storage.save.call_args[0]
    assert saved_key.startswith("polishs/")
    assert saved_bytes == "저장할 본문".encode("utf-8")

    db.add.assert_called_once()
    db.commit.assert_called_once()
    assert result["pending_version"]["storage_key"] == saved_key
    assert result["pending_version"]["version_id"]
    assert result["pending_version"]["created_at"]


@pytest.mark.asyncio
async def test_router_node_classifies_action_from_llm_response():
    original = language_model_registry._registry.get("default")
    language_model_registry.register("default", FakeListChatModel(responses=["polish"]))
    try:
        state = _base_state(
            user_action=None,
            messages=[
                HumanMessage(content="안녕하세요"),
                AIMessage(content="설명해보세요."),
                HumanMessage(content="원고 작성해주세요"),
            ],
        )
        result = await router_node(state, {"configurable": {"model": "default"}})
        assert result["user_action"] == "polish"
    finally:
        if original is not None:
            language_model_registry.register("default", original)


@pytest.mark.asyncio
async def test_router_node_routes_first_message_to_opening_without_classifier():
    original = language_model_registry._registry.get("default")
    language_model_registry.register("default", FakeListChatModel(responses=["polish"]))
    try:
        state = _base_state(user_action=None, messages=[HumanMessage(content="안녕하세요")])
        result = await router_node(state, {"configurable": {"model": "default"}})
        assert result["user_action"] == "opening"
    finally:
        if original is not None:
            language_model_registry.register("default", original)


@pytest.mark.asyncio
async def test_router_node_falls_back_to_say_on_unrecognized_response(fake_llm):
    state = _base_state(
        user_action=None,
        messages=[
            HumanMessage(content="안녕하세요"),
            AIMessage(content="설명해보세요."),
            HumanMessage(content="이건 애매합니다."),
        ],
    )

    result = await router_node(state, {"configurable": {"model": "default"}})

    assert result["user_action"] == "say"


@pytest.mark.asyncio
async def test_opening_node_uses_opening_phase_without_extra_guard():
    original = language_model_registry._registry.get("default")
    recording_model = RecordingLanguageModel()
    language_model_registry.register("default", recording_model)
    try:
        human_message = HumanMessage(content="안녕하세요")
        state = _base_state(user_action="opening", messages=[human_message])

        result = await opening_node(state, {"configurable": {"model": "default"}})

        assert result["messages"][0].content == "생성된 원고 본문"
        assert "대화 시작 단계" in recording_model.messages[0].content
        assert "안녕하세요, [사용자 닉네임]" in recording_model.messages[0].content
        assert "어떤 것을 배웠나요? 가볍게 설명해주세요" in recording_model.messages[0].content
        assert "[사용자 닉네임] 테스터" in recording_model.messages[0].content
        assert recording_model.messages[-1] is human_message
    finally:
        if original is not None:
            language_model_registry.register("default", original)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("node", "kind"),
    [(outline_node, "outline"), (polish_node, "polish")],
)
async def test_generation_nodes_append_final_output_rules_after_history(node, kind):
    expected_guard = {"outline": OUTLINE_FINAL_GUARD, "polish": POLISH_FINAL_GUARD}[kind]
    original = language_model_registry._registry.get("default")
    recording_model = RecordingLanguageModel()
    language_model_registry.register("default", recording_model)
    try:
        human_message = HumanMessage(content="표 대신 리스트로 원고 작성해주세요.")
        state = _base_state(messages=[human_message])

        result = await node(state, {"configurable": {"model": "default"}})

        assert result["pending_version"]["kind"] == kind
        assert recording_model.messages[-2] is human_message
        assert isinstance(recording_model.messages[-1], SystemMessage)
        assert recording_model.messages[-1].content == expected_guard.text
        assert "텍스트 표를 절대 넣지 마십시오" in recording_model.messages[-1].content
        assert "절대 거절하지 마십시오" in recording_model.messages[-1].content
        assert "인사말, 안내문, 코멘트, 마침말" in recording_model.messages[-1].content
    finally:
        if original is not None:
            language_model_registry.register("default", original)
