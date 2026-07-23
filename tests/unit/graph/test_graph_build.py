import pytest
from langgraph.graph import END

from app.graph.builder import (
    MAX_POLISH_ATTEMPTS,
    build_graph,
    route_after_chinese_prevent,
    route_after_polish,
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
            "polish",
            "finalize",
            "clean_polish_output",
            "refuse",
            "chinese_prevent",
            "make_new_paper",
            "evaluate_polish",
        }
        assert expected <= nodes


def test_route_after_chinese_prevent_routes_when_new_paper_exists():
    assert route_after_chinese_prevent({"new_paper": {"kind": "polish"}}) == "make_new_paper"
    assert route_after_chinese_prevent({"new_paper": None}) == END


def test_route_after_polish_retries_when_content_too_small():
    state = {"new_paper": {"kind": "polish", "content": "짧음"}, "polish_attempts": 1}
    assert route_after_polish(state) == "polish"


def test_route_after_polish_proceeds_when_content_large_enough():
    state = {
        "new_paper": {"kind": "polish", "content": "가" * 900},
        "polish_attempts": 1,
    }
    assert route_after_polish(state) == "chinese_prevent"


def test_route_after_polish_stops_retrying_at_max_attempts():
    state = {
        "new_paper": {"kind": "polish", "content": "짧음"},
        "polish_attempts": MAX_POLISH_ATTEMPTS,
    }
    assert route_after_polish(state) == "chinese_prevent"
