from app.research.agent_tools import fetch_page_tool, search_web_tool


def test_exposes_research_operations_as_ai_tools():
    """일반 실행 함수와 별도로 AI가 호출할 LangChain Tool 계약을 노출하는지 검증한다."""
    assert search_web_tool.name == "search_web"
    assert set(search_web_tool.args) == {"query", "max_results", "allowed_domains"}
    assert fetch_page_tool.name == "fetch_page"
    assert set(fetch_page_tool.args) == {"url"}
