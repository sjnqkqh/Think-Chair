import asyncio
import hashlib
from dataclasses import dataclass
from datetime import datetime, timezone
from urllib.parse import urljoin, urlsplit
from urllib.robotparser import RobotFileParser

import httpx
from lxml import etree

from app.research.contracts import (
    FetchRequest,
    FetchedSource,
    FetchResponse,
)
from app.research.network_safety import (
    AddressResolver,
    normalize_http_url,
    public_url_error,
    resolve_addresses,
)
from app.research.page_parser import parse_html_page
from app.research.retry import retry_wait_seconds

USER_AGENT = "ThinkChairResearchBot/1.0"
FETCH_TIMEOUT_SECONDS = 10
MAX_RESPONSE_BYTES = 2 * 1024 * 1024
MAX_REDIRECTS = 3
MAX_ATTEMPTS = 3
MIN_TEXT_CHARS = 40


@dataclass
class _Download:
    status_code: int = 0
    headers: httpx.Headers | None = None
    body: bytes = b""
    error_code: str | None = None
    retryable: bool = False


async def _download(client: httpx.AsyncClient, url: str) -> _Download:
    for attempt in range(MAX_ATTEMPTS):
        try:
            async with client.stream(
                "GET",
                url,
                headers={"Accept": "text/html", "User-Agent": USER_AGENT},
                follow_redirects=False,
            ) as response:
                if response.status_code == 429 or response.status_code >= 500:
                    if attempt + 1 < MAX_ATTEMPTS:
                        await asyncio.sleep(
                            retry_wait_seconds(
                                attempt,
                                response.headers.get("Retry-After"),
                            )
                        )
                        continue
                    return _Download(
                        status_code=response.status_code,
                        error_code="fetch_upstream_error",
                        retryable=True,
                    )

                body = bytearray()
                async for chunk in response.aiter_bytes():
                    body.extend(chunk)
                    if len(body) > MAX_RESPONSE_BYTES:
                        return _Download(error_code="response_too_large")
                return _Download(
                    status_code=response.status_code,
                    headers=response.headers,
                    body=bytes(body),
                )
        except httpx.TimeoutException:
            if attempt + 1 < MAX_ATTEMPTS:
                await asyncio.sleep(retry_wait_seconds(attempt))
                continue
            return _Download(error_code="fetch_timeout", retryable=True)
        except httpx.HTTPError:
            return _Download(error_code="fetch_network_error", retryable=True)
    return _Download(error_code="fetch_upstream_error", retryable=True)


async def _robots_error(
    client: httpx.AsyncClient,
    url: str,
) -> tuple[str | None, bool]:
    parsed = urlsplit(url)
    robots_url = f"{parsed.scheme}://{parsed.netloc}/robots.txt"
    result = await _download(client, robots_url)
    if result.error_code:
        return "robots_unavailable", result.retryable
    if result.status_code == 404:
        return None, False
    if not 200 <= result.status_code < 300:
        return "robots_unavailable", result.status_code >= 500

    parser = RobotFileParser()
    parser.set_url(robots_url)
    parser.parse(result.body.decode("utf-8", errors="replace").splitlines())
    if not parser.can_fetch(USER_AGENT, url):
        return "robots_disallowed", False
    return None, False


def _fingerprint(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _html_charset(headers: httpx.Headers | None) -> str:
    if headers is None:
        return "utf-8"
    content_type = headers.get("Content-Type", "")
    for part in content_type.split(";"):
        part = part.strip()
        if part.lower().startswith("charset="):
            charset = part.split("=", 1)[1].strip().strip("'\"")
            if charset:
                return charset
    return "utf-8"


async def fetch_page(
    request: FetchRequest,
    *,
    client: httpx.AsyncClient | None = None,
    resolver: AddressResolver = resolve_addresses,
) -> FetchResponse:
    current_url = normalize_http_url(request.url)
    if current_url is None:
        return FetchResponse(error_code="unsafe_url")

    owns_client = client is None
    client = client or httpx.AsyncClient(
        timeout=FETCH_TIMEOUT_SECONDS,
        follow_redirects=False,
    )
    try:
        for redirect_count in range(MAX_REDIRECTS + 1):
            if error_code := await public_url_error(current_url, resolver):
                return FetchResponse(
                    error_code=error_code,
                    retryable=error_code == "dns_resolution_failed",
                )
            robots_error, retryable = await _robots_error(client, current_url)
            if robots_error:
                return FetchResponse(error_code=robots_error, retryable=retryable)

            result = await _download(client, current_url)
            if result.error_code:
                return FetchResponse(
                    error_code=result.error_code,
                    retryable=result.retryable,
                )
            if 300 <= result.status_code < 400:
                location = (result.headers or {}).get("Location")
                if not location:
                    return FetchResponse(error_code="invalid_redirect")
                if redirect_count == MAX_REDIRECTS:
                    return FetchResponse(error_code="too_many_redirects")
                target = normalize_http_url(urljoin(current_url, location))
                if target is None:
                    return FetchResponse(error_code="unsafe_url")
                current_url = target
                continue
            if not 200 <= result.status_code < 300:
                return FetchResponse(error_code="fetch_rejected")

            media_type = (result.headers or {}).get("Content-Type", "")
            media_type = media_type.split(";", 1)[0].strip().lower()
            if media_type not in {"text/html", "application/xhtml+xml"}:
                return FetchResponse(error_code="unsupported_media_type")

            # aiter_bytes() already yields decompressed body; do not rebuild an
            # httpx.Response with Content-Encoding or it tries to decompress twice.
            html = result.body.decode(_html_charset(result.headers), errors="replace")
            try:
                page = parse_html_page(html, current_url)
            except (ValueError, TypeError, etree.LxmlError):
                return FetchResponse(error_code="extraction_failed")
            canonical_url = normalize_http_url(urljoin(current_url, page.canonical_url))
            if canonical_url is None or await public_url_error(canonical_url, resolver):
                return FetchResponse(error_code="unsafe_canonical_url")
            if not page.title or len(page.text) < MIN_TEXT_CHARS:
                return FetchResponse(error_code="insufficient_content")

            normalized_content = "\n".join(
                [" ".join(page.text.split())]
                + [" ".join(section.text.split()) for section in page.sections]
            )
            source = FetchedSource(
                **page.model_dump(exclude={"canonical_url", "publisher"}),
                requested_url=request.url,
                canonical_url=canonical_url,
                publisher=page.publisher or urlsplit(canonical_url).hostname,
                media_type=media_type,
                fetched_at=datetime.now(timezone.utc),
                content_hash=_fingerprint(normalized_content),
                source_key=_fingerprint(canonical_url),
            )
            return FetchResponse(source=source)
    finally:
        if owns_client:
            await client.aclose()

    return FetchResponse(error_code="too_many_redirects")
