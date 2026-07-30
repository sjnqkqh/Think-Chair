from pathlib import Path

import httpx
import pytest

from app.research.contracts import FetchRequest
from app.research.page_fetcher import fetch_page


FIXTURES = Path(__file__).resolve().parents[2] / "fixtures" / "research"


async def _public_resolver(hostname: str) -> list[str]:
    return ["93.184.216.34"]


def _client(handler) -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


def _robots_or_html(request: httpx.Request, html: str) -> httpx.Response:
    if request.url.path == "/robots.txt":
        return httpx.Response(200, text="User-agent: *\nAllow: /\n")
    return httpx.Response(200, headers={"Content-Type": "text/html"}, text=html)


async def test_fetches_allowed_html_with_stable_source_identity():
    """허용된 HTML에서 출처 정보와 반복 가능한 본문·URL 해시를 만드는지 검증한다."""
    html = (FIXTURES / "technical_doc.html").read_text()

    async with _client(lambda request: _robots_or_html(request, html)) as client:
        first = await fetch_page(
            FetchRequest(url="https://docs.example.com/retries"),
            client=client,
            resolver=_public_resolver,
        )
        second = await fetch_page(
            FetchRequest(url="https://docs.example.com/retries"),
            client=client,
            resolver=_public_resolver,
        )

    assert first.source is not None
    assert first.source.canonical_url == "https://docs.example.com/retries"
    assert "bounded exponential backoff" in first.source.text
    assert first.source.content_hash == second.source.content_hash
    assert first.source.source_key == second.source.source_key


@pytest.mark.parametrize(
    "blocked_address",
    ["127.0.0.1", "10.0.0.1", "169.254.169.254", "fe80::1", "::1"],
)
async def test_rejects_non_public_initial_address(blocked_address):
    """최초 URL이 로컬·사설·링크 로컬 주소를 가리키면 요청 전에 차단하는지 검증한다."""

    async def private_resolver(hostname: str) -> list[str]:
        return [blocked_address]

    def handler(request: httpx.Request) -> httpx.Response:
        raise AssertionError("network must not be called")

    async with _client(handler) as client:
        response = await fetch_page(
            FetchRequest(url="http://internal.example/admin"),
            client=client,
            resolver=private_resolver,
        )

    assert response.error_code == "unsafe_url"
    assert response.retryable is False


async def test_rejects_private_redirect_target():
    """공개 URL이 내부망으로 이동하는 우회도 이동 대상 요청 전에 차단하는지 검증한다."""
    requested_paths = []

    def handler(request: httpx.Request) -> httpx.Response:
        requested_paths.append(request.url.path)
        if request.url.path == "/robots.txt":
            return httpx.Response(200, text="User-agent: *\nAllow: /\n")
        return httpx.Response(302, headers={"Location": "http://127.0.0.1/admin"})

    async with _client(handler) as client:
        response = await fetch_page(
            FetchRequest(url="https://docs.example.com/retries"),
            client=client,
            resolver=_public_resolver,
        )

    assert response.error_code == "unsafe_url"
    assert "/admin" not in requested_paths


async def test_stops_after_redirect_limit():
    """주소 이동이 제한 횟수를 넘으면 추가 요청 없이 종료하는지 검증한다."""
    page_attempts = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal page_attempts
        if request.url.path == "/robots.txt":
            return httpx.Response(404)
        page_attempts += 1
        return httpx.Response(302, headers={"Location": f"/redirect-{page_attempts}"})

    async with _client(handler) as client:
        response = await fetch_page(
            FetchRequest(url="https://docs.example.com/start"),
            client=client,
            resolver=_public_resolver,
        )

    assert page_attempts == 4
    assert response.error_code == "too_many_redirects"


async def test_rejects_robots_disallowed_page():
    """robots.txt가 막은 경로를 본문 요청 없이 거부하는지 검증한다."""
    requested_paths = []

    def handler(request: httpx.Request) -> httpx.Response:
        requested_paths.append(request.url.path)
        return httpx.Response(200, text="User-agent: *\nDisallow: /private\n")

    async with _client(handler) as client:
        response = await fetch_page(
            FetchRequest(url="https://docs.example.com/private/report"),
            client=client,
            resolver=_public_resolver,
        )

    assert response.error_code == "robots_disallowed"
    assert requested_paths == ["/robots.txt"]


async def test_rejects_unsupported_media_type():
    """HTML이 아닌 PDF 응답을 본문으로 읽거나 파싱하지 않는지 검증한다."""

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/robots.txt":
            return httpx.Response(404)
        return httpx.Response(
            200,
            headers={"Content-Type": "application/pdf"},
            content=b"%PDF",
        )

    async with _client(handler) as client:
        response = await fetch_page(
            FetchRequest(url="https://docs.example.com/report.pdf"),
            client=client,
            resolver=_public_resolver,
        )

    assert response.error_code == "unsupported_media_type"


async def test_rejects_oversized_html(monkeypatch):
    """설정한 최대 바이트를 넘는 HTML을 끝까지 보관하지 않고 거부하는지 검증한다."""
    monkeypatch.setattr("app.research.page_fetcher.MAX_RESPONSE_BYTES", 32)

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/robots.txt":
            return httpx.Response(404)
        return httpx.Response(
            200,
            headers={"Content-Type": "text/html"},
            content=b"x" * 33,
        )

    async with _client(handler) as client:
        response = await fetch_page(
            FetchRequest(url="https://docs.example.com/large"),
            client=client,
            resolver=_public_resolver,
        )

    assert response.error_code == "response_too_large"


@pytest.mark.parametrize("temporary_status", [429, 503])
async def test_retries_one_temporary_server_error(temporary_status):
    """원문 서버의 일시적인 호출 제한·5xx 오류를 한 번만 재시도하는지 검증한다."""
    html = (FIXTURES / "vendor_blog.html").read_text()
    page_attempts = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal page_attempts
        if request.url.path == "/robots.txt":
            return httpx.Response(404)
        page_attempts += 1
        if page_attempts == 1:
            return httpx.Response(temporary_status, headers={"Retry-After": "0"})
        return httpx.Response(200, headers={"Content-Type": "text/html"}, text=html)

    async with _client(handler) as client:
        response = await fetch_page(
            FetchRequest(url="https://engineering.example.com/queue-latency"),
            client=client,
            resolver=_public_resolver,
        )

    assert page_attempts == 2
    assert response.source is not None


async def test_rejects_private_canonical_url():
    """본문의 대표 URL이 내부망을 가리키면 공용 출처 식별자로 채택하지 않는지 검증한다."""
    html = """
    <html><head><title>Unsafe canonical</title>
    <link rel="canonical" href="http://127.0.0.1/admin"></head>
    <body><main><p>This public-looking page contains enough useful text to pass
    the normal minimum content requirement before canonical validation.</p></main></body>
    </html>
    """

    async with _client(lambda request: _robots_or_html(request, html)) as client:
        response = await fetch_page(
            FetchRequest(url="https://docs.example.com/report"),
            client=client,
            resolver=_public_resolver,
        )

    assert response.error_code == "unsafe_canonical_url"


async def test_returns_retryable_error_after_timeout(monkeypatch):
    """원문 시간 초과를 지수 백오프로 제한 재시도한 뒤 구조화된 오류로 반환하는지 검증한다."""
    page_attempts = 0
    delays = []

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal page_attempts
        if request.url.path == "/robots.txt":
            return httpx.Response(404)
        page_attempts += 1
        raise httpx.ReadTimeout("slow", request=request)

    async def record_delay(delay: float) -> None:
        delays.append(delay)

    monkeypatch.setattr("app.research.page_fetcher.asyncio.sleep", record_delay)
    async with _client(handler) as client:
        response = await fetch_page(
            FetchRequest(url="https://docs.example.com/slow"),
            client=client,
            resolver=_public_resolver,
        )

    assert page_attempts == 3
    assert delays == [0.25, 0.5]
    assert response.error_code == "fetch_timeout"
    assert response.retryable is True


async def test_returns_extraction_error_for_malformed_html():
    """깨진 HTML 파싱 실패가 조사 작업 전체를 중단시키는 예외로 새지 않는지 검증한다."""

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/robots.txt":
            return httpx.Response(404)
        return httpx.Response(200, headers={"Content-Type": "text/html"}, text="")

    async with _client(handler) as client:
        response = await fetch_page(
            FetchRequest(url="https://docs.example.com/broken"),
            client=client,
            resolver=_public_resolver,
        )

    assert response.error_code == "extraction_failed"
    assert response.retryable is False
