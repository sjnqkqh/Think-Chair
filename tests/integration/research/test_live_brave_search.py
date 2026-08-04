import os

import pytest

from app.core.config import settings
from app.research.contracts import FetchRequest, SearchRequest
from app.research.page_fetcher import fetch_page
from app.research.web_search import search_web


pytestmark = [
    pytest.mark.integration,
    pytest.mark.live_web,
    pytest.mark.skipif(
        os.getenv("RUN_LIVE_WEB_TESTS") != "1",
        reason="RUN_LIVE_WEB_TESTS=1일 때만 실제 Brave Search를 호출한다.",
    ),
    pytest.mark.skipif(
        not settings.BRAVE_SEARCH_API_KEY,
        reason="BRAVE_SEARCH_API_KEY가 설정되어 있어야 한다.",
    ),
]


async def test_live_brave_search_returns_normalized_hits():
    """실제 Brave Search가 URL·제목·snippet이 있는 검색 결과를 반환하는지 검증한다."""
    response = await search_web(
        SearchRequest(
            query="Bank of Korea GDP growth rate 2024",
            max_results=3,
        )
    )

    assert response.error_code is None, response.error_code
    assert len(response.results) >= 1
    first = response.results[0]
    assert first.url.startswith("https://")
    assert first.title
    assert first.provider_rank == 1


async def test_live_brave_search_then_fetch_yields_page_text():
    """Brave 검색 결과 URL 중 하나에서 원문 본문을 실제로 수집할 수 있는지 검증한다."""
    search_response = await search_web(
        SearchRequest(
            query="Korea GDP official statistics",
            max_results=3,
        )
    )
    assert search_response.error_code is None, search_response.error_code
    assert search_response.results

    fetched_text_lengths: list[int] = []
    for hit in search_response.results:
        fetch_response = await fetch_page(FetchRequest(url=hit.url))
        if fetch_response.source is None:
            continue
        fetched_text_lengths.append(len(fetch_response.source.text))
        if fetch_response.source.text.strip():
            break

    assert fetched_text_lengths, "검색된 URL에서 본문을 하나도 수집하지 못했다"
    assert max(fetched_text_lengths) > 100
