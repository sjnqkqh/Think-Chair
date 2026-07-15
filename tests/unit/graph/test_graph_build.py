import pytest
from langgraph.graph import END

from app.graph.builder import build_graph, route_after_chinese_prevent
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
            "chinese_prevent",
            "make_new_paper",
        }
        assert expected <= nodes


def test_route_after_chinese_prevent_routes_when_new_paper_exists():
    assert route_after_chinese_prevent({"new_paper": {"kind": "polish"}}) == "make_new_paper"
    assert route_after_chinese_prevent({"new_paper": None}) == END
