import unicodedata
import uuid
from datetime import datetime, timezone
from pathlib import Path

import pytest
from langchain_text_splitters import RecursiveCharacterTextSplitter

from app.research.chunking import (
    CHUNK_OVERLAP,
    CHUNK_SCHEMA_VERSION,
    CHUNK_SIZE,
    chunk_source,
    detect_language,
)
from app.research.contracts import ExtractedSection, FetchedSource
from app.research.page_parser import parse_html_page

FIXTURES = Path(__file__).resolve().parents[2] / "fixtures" / "research"


def _source(text: str, *, sections: list[ExtractedSection] | None = None):
    return FetchedSource(
        requested_url="https://example.com/requested",
        canonical_url="https://example.com/canonical",
        title="청킹 테스트",
        publisher="Example",
        published_at=None,
        text=text,
        sections=sections or [],
        media_type="text/html",
        fetched_at=datetime.now(timezone.utc),
        content_hash="content-hash",
        source_key="source-key",
    )


@pytest.fixture(autouse=True)
def offline_splitter(monkeypatch):
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=CHUNK_SIZE,
        chunk_overlap=CHUNK_OVERLAP,
        length_function=len,
        separators=["\n\n", "\n", "。", ". ", " ", ""],
        keep_separator="end",
        add_start_index=True,
    )
    monkeypatch.setattr("app.research.chunking._splitter", lambda: splitter)


def test_chunks_plain_text_by_structure_within_token_limit():
    """마크다운이 아닌 긴 원문도 구조 경계를 우선하는 600/100 규칙으로 나누는지 검증한다."""
    paragraphs = [
        f"문단 {index}. " + "처리량과 지연 시간을 함께 관찰해야 합니다. " * 90
        for index in range(8)
    ]

    chunks = chunk_source(_source("\n\n".join(paragraphs)), uuid.uuid4())
    assert len(chunks) > 1
    assert CHUNK_SIZE == 600
    assert CHUNK_OVERLAP == 100
    assert all(len(chunk.text) <= CHUNK_SIZE for chunk in chunks)
    assert all(chunk.chunk_schema_version == CHUNK_SCHEMA_VERSION for chunk in chunks)
    assert chunks[0].text.startswith("문단 0.")


def test_normalizes_unicode_and_preserves_section_source_urls():
    """원문은 NFC로 통일하고 댓글 청크는 대표 URL과 댓글 고유 주소를 함께 보존하는지 검증한다."""
    comment_url = "https://example.com/thread/comment-1"
    source = _source(
        "Cafe\u0301 본문입니다.",
        sections=[
            ExtractedSection(
                kind="comment",
                text="댓글 근거입니다.",
                permalink=comment_url,
            )
        ],
    )

    chunks = chunk_source(source, uuid.uuid4())

    assert all(unicodedata.is_normalized("NFC", chunk.text) for chunk in chunks)
    assert chunks[0].source_url == source.canonical_url
    assert chunks[-1].source_url == comment_url
    assert chunks[-1].section_kind == "comment"
    assert [chunk.ordinal for chunk in chunks] == list(range(len(chunks)))
    assert len({chunk.id for chunk in chunks}) == len(chunks)


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("처리량과 지연 시간을 함께 측정합니다.", "ko"),
        ("Measure throughput and latency together.", "en"),
        ("처리량 throughput 과 지연 latency 를 함께 봅니다.", "mixed"),
    ],
)
def test_labels_multilingual_content_without_splitting_by_language(text, expected):
    """한국어·영어·혼합 원문을 번역하거나 격리하지 않고 검색용 언어 정보만 붙이는지 검증한다."""
    assert detect_language(text) == expected


def test_chunks_extracted_technical_document_fixture():
    """실제 HTML fixture에서 추출한 기술 문서 본문도 같은 청킹 계약으로 처리하는지 검증한다."""
    page = parse_html_page(
        (FIXTURES / "technical_doc.html").read_text(),
        "https://docs.example.com/retries",
    )

    chunks = chunk_source(_source(page.text), uuid.uuid4())

    assert chunks
    assert "bounded exponential backoff" in " ".join(
        chunk.text for chunk in chunks
    )
