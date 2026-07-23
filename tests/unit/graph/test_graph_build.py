import pytest
from langgraph.graph import END

from app.graph.builder import (
    MAX_DOCUMENT_GENERATION_ATTEMPTS,
    build_graph,
    route_after_chinese_prevent,
    route_after_generate_document_from_conversation,
)
from app.graph.checkpointer import make_checkpointer

pytestmark = pytest.mark.unit


@pytest.mark.asyncio
async def test_build_graph_wires_all_expected_nodes():
    async with make_checkpointer(":memory:") as checkpointer:
        graph = build_graph(checkpointer)
        nodes = {n for n in graph.nodes if n != "__start__"}
        expected = {
            "router",
            "opening",
            "converse",
            "feedback",
            "outline",
            "generate_document_from_conversation",
            "refuse",
            "chinese_prevent",
            "save_new_paper",
            "evaluate_document",
        }
        assert expected <= nodes


def test_route_after_chinese_prevent_routes_when_new_paper_exists():
    assert (
        route_after_chinese_prevent({"new_paper": {"kind": "document"}})
        == "save_new_paper"
    )
    assert route_after_chinese_prevent({"new_paper": None}) == END


def test_route_after_generate_document_from_conversation_retries_when_content_too_small():
    state = {
        "new_paper": {"kind": "document", "content": "짧음"},
        "document_generation_attempts": 1,
    }
    assert (
        route_after_generate_document_from_conversation(state)
        == "generate_document_from_conversation"
    )


def test_route_after_generate_document_from_conversation_proceeds_when_content_large_enough():
    state = {
        "new_paper": {"kind": "document", "content": "가" * 900},
        "document_generation_attempts": 1,
    }
    assert route_after_generate_document_from_conversation(state) == "chinese_prevent"


def test_route_after_generate_document_from_conversation_stops_retrying_at_max_attempts():
    state = {
        "new_paper": {"kind": "document", "content": "짧음"},
        "document_generation_attempts": MAX_DOCUMENT_GENERATION_ATTEMPTS,
    }
    assert route_after_generate_document_from_conversation(state) == "chinese_prevent"
