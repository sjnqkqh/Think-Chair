import httpx
import pytest
from pydantic import ValidationError

from app.research.contracts import SearchRequest
from app.research.web_search import search_web


def _client(handler) -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


async def test_normalizes_brave_results_and_enforces_request_limits():
    """Brave 결과를 공통 형식으로 바꾸고 허용 도메인과 결과 수를 강제하는지 검증한다."""

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["X-Subscription-Token"] == "brave-key"
        assert request.url.params["count"] == "2"
        return httpx.Response(
            200,
            json={
                "web": {
                    "results": [
                        {
                            "url": "https://docs.example.com/first",
                            "title": "First",
                            "description": "first result",
                            "profile": {"long_name": "Example Docs"},
                            "age": "July 1, 2026",
                        },
                        {
                            "url": "https://blocked.example.net/second",
                            "title": "Blocked",
                            "description": "must be filtered",
                        },
                        {
                            "url": "https://blog.example.com/third",
                            "title": "Third",
                            "description": "third result",
                        },
                    ]
                }
            },
        )

    async with _client(handler) as client:
        response = await search_web(
            SearchRequest(
                query="bounded retries",
                max_results=2,
                allowed_domains=["example.com"],
            ),
            client=client,
            api_key="brave-key",
        )

    assert [hit.title for hit in response.results] == ["First", "Third"]
    assert response.results[0].publisher == "Example Docs"
    assert response.results[0].provider_rank == 1
    assert response.error_code is None


async def test_retries_one_rate_limit_response():
    """Brave의 일시적인 호출 제한은 한 번만 재시도해 회복 가능한지 검증한다."""
    attempts = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            return httpx.Response(429, headers={"Retry-After": "0"})
        return httpx.Response(200, json={"web": {"results": []}})

    async with _client(handler) as client:
        response = await search_web(
            SearchRequest(query="queue latency"),
            client=client,
            api_key="brave-key",
        )

    assert attempts == 2
    assert response.error_code is None


async def test_ignores_non_http_provider_result():
    """검색 제공자가 잘못된 스킴을 반환해도 후속 수집 후보에 포함하지 않는지 검증한다."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "web": {
                    "results": [
                        {
                            "url": "javascript:alert(1)",
                            "title": "Unsafe",
                            "description": "must be filtered",
                        },
                        {
                            "url": "https://docs.example.com/safe#section",
                            "title": "Safe",
                            "description": "safe result",
                        },
                    ]
                }
            },
        )

    async with _client(handler) as client:
        response = await search_web(
            SearchRequest(query="safe source"),
            client=client,
            api_key="brave-key",
        )

    assert [hit.url for hit in response.results] == ["https://docs.example.com/safe"]


async def test_returns_retryable_error_after_timeout(monkeypatch):
    """검색 시간 초과를 지수 백오프로 제한 재시도한 뒤 구조화된 오류로 반환하는지 검증한다."""
    attempts = 0
    delays = []

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        raise httpx.ReadTimeout("slow", request=request)

    async def record_delay(delay: float) -> None:
        delays.append(delay)

    monkeypatch.setattr("app.research.web_search.asyncio.sleep", record_delay)
    async with _client(handler) as client:
        response = await search_web(
            SearchRequest(query="queue latency"),
            client=client,
            api_key="brave-key",
        )

    assert attempts == 3
    assert delays == [0.25, 0.5]
    assert response.results == []
    assert response.error_code == "search_timeout"
    assert response.retryable is True


async def test_returns_retryable_error_after_network_failure():
    """검색 연결 실패가 호출자를 중단시키는 예외 대신 구조화된 오류가 되는지 검증한다."""

    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("offline", request=request)

    async with _client(handler) as client:
        response = await search_web(
            SearchRequest(query="queue latency"),
            client=client,
            api_key="brave-key",
        )

    assert response.error_code == "search_network_error"
    assert response.retryable is True


async def test_returns_error_for_malformed_provider_payload():
    """검색 제공자의 예상 밖 응답 구조를 빈 정상 결과로 오인하지 않는지 검증한다."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=[])

    async with _client(handler) as client:
        response = await search_web(
            SearchRequest(query="queue latency"),
            client=client,
            api_key="brave-key",
        )

    assert response.error_code == "search_invalid_response"
    assert response.results == []


async def test_rejects_missing_api_key_without_network_call():
    """API 키가 없을 때 외부 요청 없이 설정 오류를 알려주는지 검증한다."""

    def handler(request: httpx.Request) -> httpx.Response:
        raise AssertionError("network must not be called")

    async with _client(handler) as client:
        response = await search_web(
            SearchRequest(query="queue latency"),
            client=client,
            api_key="",
        )

    assert response.error_code == "search_not_configured"
    assert response.retryable is False


def test_rejects_query_over_brave_word_limit():
    """Brave가 받지 못하는 50단어 초과 검색어를 외부 요청 전에 거부하는지 검증한다."""
    with pytest.raises(ValidationError):
        SearchRequest(query=" ".join(["word"] * 51))
