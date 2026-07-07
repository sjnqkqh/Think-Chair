from unittest.mock import MagicMock

import pytest
from langchain_core.language_models.fake_chat_models import FakeListChatModel
from langchain_core.messages import AIMessage, HumanMessage

from app.graph import llm_registry
from app.graph.nodes.chinese_prevent import chinese_prevent_node
from app.graph.nodes.persist_version import persist_version_node
from app.graph.nodes.router import router_node


def _base_state(**overrides):
    state = {
        "manuscript_id": "11111111-1111-1111-1111-111111111111",
        "concept": "til",
        "topic": "테스트 주제",
        "audience_level": None,
        "user_action": "polish",
        "messages": [HumanMessage(content="원고를 작성해줘")],
        "pending_version": None,
    }
    state.update(overrides)
    return state

def test_chinese_prevent_node_removes_chinese_from_message_and_pending_version():
    state = _base_state(
        messages=[AIMessage(content="漢字テスト 결과", id="msg-1")],
        pending_version={"kind": "polish", "content": "漢字テスト 본문"},
    )

    result = chinese_prevent_node(state)

    assert "漢字" not in result["messages"][0].content
    assert result["messages"][0].id == "msg-1"
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


@pytest.mark.asyncio
async def test_router_node_classifies_action_from_llm_response():
    original = llm_registry._registry.get("default")
    llm_registry.register("default", FakeListChatModel(responses=["polish"]))
    try:
        state = _base_state(user_action=None, messages=[HumanMessage(content="원고 작성해주세요")])
        result = await router_node(state, {"configurable": {"model": "default"}})
        assert result["user_action"] == "polish"
    finally:
        if original is not None:
            llm_registry.register("default", original)


@pytest.mark.asyncio
async def test_router_node_falls_back_to_say_on_unrecognized_response(fake_llm):
    state = _base_state(user_action=None, messages=[HumanMessage(content="안녕하세요")])

    result = await router_node(state, {"configurable": {"model": "default"}})

    assert result["user_action"] == "say"
