from pathlib import Path

import pytest

from app.research.page_parser import parse_html_page


FIXTURES = Path(__file__).resolve().parents[2] / "fixtures" / "research"


@pytest.mark.parametrize(
    ("fixture_name", "url", "expected_text"),
    [
        (
            "technical_doc.html",
            "https://docs.example.com/retries",
            "bounded exponential backoff",
        ),
        (
            "vendor_blog.html",
            "https://engineering.example.com/queue-latency",
            "240 milliseconds",
        ),
        (
            "benchmark.html",
            "https://benchmarks.example.com/parsers",
            "Candidate",
        ),
        (
            "huggingface_model_card.html",
            "https://huggingface.co/ExampleOrg/example-model",
            "multilingual embedding model",
        ),
    ],
)
def test_extracts_required_html_document_types(fixture_name, url, expected_text):
    """1차 지원 대상 HTML에서 근거가 되는 본문과 표를 잃지 않는지 검증한다."""
    html = (FIXTURES / fixture_name).read_text()

    page = parse_html_page(html, url)

    assert expected_text in page.text
    assert page.title
    assert "system prompt" not in page.text


def test_extracts_reddit_post_and_limited_comment_tree():
    """Reddit 본문과 루트 댓글 10개·답글 한 단계만 출처 링크와 함께 추출하는지 검증한다."""
    html = (FIXTURES / "reddit_thread.html").read_text()

    page = parse_html_page(
        html,
        "https://www.reddit.com/r/Example/comments/abc123/what_changed/",
    )

    assert "benchmark result changed" in page.text
    assert [section.kind for section in page.sections].count("comment") == 10
    assert [section.kind for section in page.sections].count("reply") == 1
    assert all(section.permalink.startswith("https://www.reddit.com/") for section in page.sections)
    combined = "\n".join(section.text for section in page.sections)
    assert "Reply 01 supplies" in combined
    assert "too deep" not in combined
    assert "Root comment 11" not in combined
