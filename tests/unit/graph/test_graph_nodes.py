from unittest.mock import MagicMock

import pytest
from langchain_core.language_models.fake_chat_models import FakeListChatModel
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

from app.graph import llm_registry as language_model_registry
from app.graph.nodes.chinese_prevent import chinese_prevent_node
from app.graph.nodes.clean_polish_output import clean_polish_output_node
from app.graph.nodes.converse import converse_node
from app.graph.nodes.feedback import feedback_node
from app.graph.nodes.opening import opening_node
from app.graph.nodes.outline import outline_node
from app.graph.nodes.make_new_paper import make_new_paper_node
from app.graph.nodes.polish import polish_node
from app.graph.router.intent_router import router_node
from app.graph.prompts.phases.outline import OUTLINE_FINAL_GUARD
from app.graph.prompts.phases.polish import POLISH_FINAL_GUARD

pytestmark = pytest.mark.unit


def _base_state(**overrides):
    state = {
        "manuscript_id": "11111111-1111-1111-1111-111111111111",
        "concept": "TIL",
        "topic": "테스트 주제",
        "user_nickname": "테스터",
        "audience_level": None,
        "user_action": "polish",
        "messages": [HumanMessage(content="원고를 작성해줘")],
        "client_message": None,
        "new_paper": None,
    }
    state.update(overrides)
    return state


class RecordingLanguageModel:
    def __init__(self):
        self.messages = None

    async def ainvoke(self, messages):
        self.messages = messages
        return AIMessage(content="생성된 원고 본문")


def test_chinese_prevent_node_removes_chinese_from_message_and_new_paper():
    state = _base_state(
        messages=[AIMessage(content="漢字テスト 결과", id="message-1")],
        client_message="漢字테스트 안내",
        new_paper={"kind": "polish", "content": "漢字テスト 본문"},
    )

    result = chinese_prevent_node(state)

    assert "漢字" not in result["messages"][0].content
    assert result["messages"][0].id == "message-1"
    assert "漢字" not in result["client_message"]
    assert "漢字" not in result["new_paper"]["content"]


def test_clean_polish_output_node_removes_generation_preface_and_closing(caplog):
    preface = (
        "작성되었습니다. 전체 분량은 약 8개 섹션으로 구성되어 있으며, "
        "부트캠프 3개월 차 수강생이 읽을 수준에 맞추었습니다."
    )
    body = "# 트랜스포머\n\n트랜스포머는 어텐션을 사용하는 모델입니다."
    closing = "검토해 보시고 수정이 필요하면 말씀해 주세요."
    state = _base_state(
        polish_attempts=1,
        new_paper={"kind": "polish", "content": f"{preface}\n\n{body}\n\n{closing}"},
    )

    result = clean_polish_output_node(state)

    assert result["new_paper"]["content"] == body
    assert "polish_output.meta_removed" in caplog.records[-1].message
    assert "content_bytes_before" in caplog.records[-1].message
    assert preface not in caplog.records[-1].message


def test_clean_polish_output_node_keeps_regular_markdown_unchanged():
    body = "# 작성 과정\n\n작성 과정에서 검토해 볼 항목을 정리합니다."

    result = clean_polish_output_node(
        _base_state(new_paper={"kind": "polish", "content": body})
    )

    assert result == {}


def test_clean_polish_output_node_keeps_body_with_broad_meta_words():
    body = (
        "전체 구성은 문제 정의, 해결 방법, 한계 순서로 설명합니다.\n\n"
        "수강생이 작성할 때에는 각 단락의 근거를 확인해야 합니다.\n\n"
        "원하시면 다음 절에서 성능 최적화를 적용할 수 있습니다."
    )

    result = clean_polish_output_node(
        _base_state(new_paper={"kind": "polish", "content": body})
    )

    assert result == {}


def test_make_new_paper_node_saves_to_storage_and_database():
    storage = MagicMock()
    database_session = MagicMock()
    database_session.query.return_value.filter.return_value.order_by.return_value.first.return_value = (
        None
    )

    state = _base_state(new_paper={"kind": "polish", "content": "저장할 본문"})
    configuration = {
        "configurable": {"storage": storage, "db_session": database_session}
    }

    result = make_new_paper_node(state, configuration)

    storage.save.assert_called_once()
    saved_key, saved_bytes = storage.save.call_args[0]
    assert saved_key.startswith("polishs/")
    assert saved_bytes == "저장할 본문".encode("utf-8")

    database_session.add.assert_called_once()
    database_session.commit.assert_called_once()
    assert result["new_paper"]["storage_key"] == saved_key
    assert result["new_paper"]["version_id"]
    assert result["new_paper"]["created_at"]


@pytest.mark.asyncio
async def test_router_node_classifies_action_from_llm_response():
    original = language_model_registry._registry.get("default")
    # 분류("polish") 이후 충분성 게이트가 호출되므로 JSON 판정 응답을 함께 제공한다.
    language_model_registry.register(
        "default",
        FakeListChatModel(
            responses=["polish", '{"sufficient": true, "reason": "근거 충분"}']
        ),
    )
    try:
        state = _base_state(
            user_action=None,
            messages=[
                HumanMessage(content="어텐션을 백엔드 개발자에게 설명하고 싶어. " * 3),
                AIMessage(content="이 주제에서 어디까지 이해하고 있나요?"),
                HumanMessage(content="RNN은 알지만 트랜스포머는 처음인 사람들이야. " * 3),
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
        state = _base_state(
            user_action=None, messages=[HumanMessage(content="안녕하세요")]
        )
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
        assert result["client_message"] == "생성된 원고 본문"
        assert "대화 시작 단계" in recording_model.messages[0].content
        assert "안녕하세요, [사용자 닉네임]" in recording_model.messages[0].content
        assert (
            "어떤 것을 배웠나요? 가볍게 설명해주세요"
            in recording_model.messages[0].content
        )
        assert "[사용자 닉네임] 테스터" in recording_model.messages[0].content
        assert recording_model.messages[-1] is human_message
    finally:
        if original is not None:
            language_model_registry.register("default", original)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("node", "user_action"),
    [(converse_node, "say"), (feedback_node, "feedback")],
)
async def test_response_nodes_return_context_message_and_client_message(
    node, user_action
):
    original = language_model_registry._registry.get("default")
    recording_model = RecordingLanguageModel()
    language_model_registry.register("default", recording_model)
    try:
        human_message = HumanMessage(content="답변해주세요.")
        state = _base_state(user_action=user_action, messages=[human_message])

        result = await node(state, {"configurable": {"model": "default"}})

        assert result["messages"][0].content == "생성된 원고 본문"
        assert result["client_message"] == "생성된 원고 본문"
        if user_action == "say":
            assert recording_model.messages[-2] is human_message
            assert isinstance(recording_model.messages[-1], SystemMessage)
        else:
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
    expected_guard = {"outline": OUTLINE_FINAL_GUARD, "polish": POLISH_FINAL_GUARD}[
        kind
    ]
    original = language_model_registry._registry.get("default")
    recording_model = RecordingLanguageModel()
    language_model_registry.register("default", recording_model)
    try:
        human_message = HumanMessage(content="표 대신 리스트로 원고 작성해주세요.")
        state = _base_state(messages=[human_message])

        result = await node(state, {"configurable": {"model": "default"}})

        assert result["new_paper"]["kind"] == kind
        assert result["client_message"]
        assert "messages" not in result
        assert recording_model.messages[-2] is human_message
        assert isinstance(recording_model.messages[-1], SystemMessage)
        assert recording_model.messages[-1].content == expected_guard.text
        assert "텍스트 표를 절대 넣지 마십시오" in recording_model.messages[-1].content
        if kind == "outline":
            assert "절대 거절하지 마십시오" in recording_model.messages[-1].content
        assert "인사말, 안내문, 코멘트, 마침말" in recording_model.messages[-1].content
    finally:
        if original is not None:
            language_model_registry.register("default", original)
