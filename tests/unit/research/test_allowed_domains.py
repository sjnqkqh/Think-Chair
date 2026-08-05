import pytest

from app.research.allowed_domains import (
    RESEARCH_ALLOWED_DOMAINS,
    url_is_allowed,
)


pytestmark = pytest.mark.unit


def test_allowlist_includes_curated_safe_domains_and_excludes_github():
    assert "medium.com" in RESEARCH_ALLOWED_DOMAINS
    assert "reddit.com" in RESEARCH_ALLOWED_DOMAINS
    assert "huggingface.co" in RESEARCH_ALLOWED_DOMAINS
    assert "cursor.com" in RESEARCH_ALLOWED_DOMAINS
    assert "cursor.sh" in RESEARCH_ALLOWED_DOMAINS
    assert "openai.com" in RESEARCH_ALLOWED_DOMAINS
    assert "github.com" not in RESEARCH_ALLOWED_DOMAINS
    assert "github.io" not in RESEARCH_ALLOWED_DOMAINS


@pytest.mark.parametrize(
    ("url", "allowed"),
    [
        ("https://docs.python.org/3/library/asyncio.html", True),
        ("https://blog.tistory.com/post/1", True),
        ("https://docs.cursor.com/agents", True),
        ("https://github.com/foo/bar", False),
        ("https://user.github.io/page", False),
        ("https://evil.example/phish", False),
    ],
)
def test_url_is_allowed_matches_suffix_domains(url: str, allowed: bool):
    assert url_is_allowed(url) is allowed
