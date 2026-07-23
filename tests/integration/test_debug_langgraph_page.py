import pytest

pytestmark = pytest.mark.integration


def test_langgraph_debug_page_renders_compiled_graph(client):
    response = client.get("/debug/langgraph")

    assert response.status_code == 200
    assert "LangGraph 노드 구조" in response.text
    assert "노드 10개" in response.text
    assert "전이 18개" in response.text
    assert "노드 목록" in response.text
    assert "router(router)" in response.text
    assert "make_new_paper" in response.text
    assert "evaluate_polish" in response.text
    assert "mermaid" in response.text
