import pytest

from app.graph.builder import build_graph
from app.graph.checkpointer import make_checkpointer


@pytest.mark.asyncio
async def test_build_graph_compiles_with_nine_nodes():
    async with make_checkpointer(":memory:") as checkpointer:
        graph = build_graph(checkpointer)
        nodes = [n for n in graph.nodes if n != "__start__"]
        assert len(nodes) == 9
        for name in (
            "router",
            "opening",
            "converse",
            "feedback",
            "outline",
            "polish",
            "finalize",
            "chinese_prevent",
            "persist_version",
        ):
            assert name in nodes
