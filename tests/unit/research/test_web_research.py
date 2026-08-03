from datetime import datetime, timezone
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from app.research.contracts import (
    FetchResponse,
    FetchedSource,
    ResearchIndexRequest,
    ResearchIndexResult,
    SearchHit,
    SearchResponse,
)
from app.research.web_research import expand_evidence_via_web_search

pytestmark = pytest.mark.unit


@pytest.mark.asyncio
async def test_expand_evidence_via_web_search_indexes_fetched_hits():
    search = AsyncMock(
        return_value=SearchResponse(
            results=[
                SearchHit(
                    url="https://docs.example/timeout",
                    title="Timeout",
                    snippet="360분",
                    provider_rank=1,
                )
            ]
        )
    )
    fetched = FetchedSource(
        requested_url="https://docs.example/timeout",
        canonical_url="https://docs.example/timeout",
        title="Timeout",
        publisher="Example",
        published_at="2026-01-01",
        text="기본 job timeout은 360분이다. " * 20,
        sections=[],
        media_type="text/html",
        fetched_at=datetime.now(timezone.utc),
        content_hash="hash",
        source_key="key",
    )
    fetch = AsyncMock(return_value=FetchResponse(source=fetched))
    index = AsyncMock(
        return_value=ResearchIndexResult(
            status="completed",
            indexed_source_ids=[uuid4()],
            chunk_count=1,
        )
    )
    job = type(
        "Job",
        (),
        {
            "id": uuid4(),
            "user_id": uuid4(),
            "manuscript_id": uuid4(),
        },
    )()

    await expand_evidence_via_web_search(
        db=object(),
        job=job,
        query="timeout 기본값",
        evidence_index=object(),
        storage=object(),
        embeddings=object(),
        search_web=search,
        fetch_page=fetch,
        index_research_sources=index,
        admit_source=lambda _source: "public",
        max_fetches=2,
    )

    search.assert_awaited_once()
    fetch.assert_awaited_once()
    index.assert_awaited_once()
    request = index.await_args.args[0]
    assert isinstance(request, ResearchIndexRequest)
    assert request.sources[0].canonical_url == "https://docs.example/timeout"
