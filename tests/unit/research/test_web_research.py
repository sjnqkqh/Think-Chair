from datetime import datetime, timezone
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.models.manuscript import ConceptType, Manuscript, ManuscriptStatus
from app.models.research import ResearchUsage
from app.models.user import User
from app.research.contracts import (
    FetchResponse,
    FetchedSource,
    ResearchIndexRequest,
    ResearchIndexResult,
    SearchHit,
    SearchResponse,
)
from app.research.web_research import expand_evidence_via_web_search
from tests.db_setup import prepare_test_database

pytestmark = pytest.mark.unit


@pytest.mark.asyncio
async def test_expand_evidence_via_web_search_indexes_fetched_hits(monkeypatch):
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
    monkeypatch.setattr(
        "app.research.web_research.research_repo.increment_research_search_count",
        lambda *args, **kwargs: None,
    )

    class _Db:
        def commit(self):
            return None

    await expand_evidence_via_web_search(
        db=_Db(),
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


@pytest.mark.asyncio
async def test_expand_evidence_increments_manuscript_search_count(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'web.db'}")
    prepare_test_database(engine)
    db = sessionmaker(bind=engine)()
    user = User(login_id="search-count", password_hash="x", nickname="s")
    db.add(user)
    db.flush()
    manuscript = Manuscript(
        user_id=user.id,
        topic="search",
        concept=ConceptType.TECH_DEEPDIVE,
        status=ManuscriptStatus.DRAFTING,
    )
    db.add(manuscript)
    db.commit()

    search = AsyncMock(return_value=SearchResponse(results=[]))
    job = type(
        "Job",
        (),
        {"id": uuid4(), "user_id": user.id, "manuscript_id": manuscript.id},
    )()

    error = await expand_evidence_via_web_search(
        db=db,
        job=job,
        query="일반론",
        evidence_index=object(),
        storage=object(),
        embeddings=object(),
        search_web=search,
        fetch_page=AsyncMock(),
        index_research_sources=AsyncMock(),
        admit_source=lambda _source: "public",
    )

    assert error == "search_empty"
    usage = (
        db.query(ResearchUsage)
        .filter(ResearchUsage.manuscript_id == manuscript.id)
        .one()
    )
    assert usage.search_count == 1
    db.close()
