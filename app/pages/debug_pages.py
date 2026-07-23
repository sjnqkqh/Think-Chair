from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

from app.graph.builder import build_graph
from app.templates.jinja import make_templates

router = APIRouter(tags=["debug"])
templates = make_templates()


@router.get("/debug/langgraph", response_class=HTMLResponse)
async def langgraph_debug(request: Request):
    """Render the graph compiled by the running application for inspection."""
    graph = getattr(request.app.state, "graph", None) or build_graph(None)
    graph_view = graph.get_graph(xray=True)
    nodes = [node for node in graph_view.nodes if node not in {"__start__", "__end__"}]

    return templates.TemplateResponse(
        request,
        "debug/langgraph.html",
        {
            "mermaid_source": graph_view.draw_mermaid(),
            "nodes": nodes,
            "node_count": len(nodes),
            "edge_count": len(graph_view.edges),
        },
    )
