"""조사 웹 검색·수집에 허용하는 도메인 목록과 검사."""

from __future__ import annotations

from urllib.parse import urlsplit

# 큐레이션 allowlist. github.com / github.io 는 1차에서 제외.
RESEARCH_ALLOWED_DOMAINS: frozenset[str] = frozenset(
    {
        # 커뮤니티·블로그
        "medium.com",
        "tistory.com",
        "velog.io",
        "dev.to",
        "hashnode.dev",
        "hashnode.com",
        "freecodecamp.org",
        # 토론·Q&A
        "reddit.com",
        "stackoverflow.com",
        "stackexchange.com",
        "news.ycombinator.com",
        "lobste.rs",
        # ML·연구
        "huggingface.co",
        "arxiv.org",
        "paperswithcode.com",
        # 공식·레퍼런스·벤더
        "docs.python.org",
        "developer.mozilla.org",
        "readthedocs.io",
        "pytorch.org",
        "tensorflow.org",
        "langchain.com",
        "openai.com",
        "anthropic.com",
        "deepseek.com",
        # Cursor
        "cursor.com",
        "cursor.sh",
    }
)


def hostname_is_allowed(hostname: str | None) -> bool:
    if not hostname:
        return False
    host = hostname.lower().rstrip(".")
    return any(
        host == domain or host.endswith(f".{domain}")
        for domain in RESEARCH_ALLOWED_DOMAINS
    )


def url_is_allowed(url: str) -> bool:
    return hostname_is_allowed(urlsplit(url).hostname)
