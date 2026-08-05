import logging
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from app.models.research import ResearchJob
from app.research.contracts import (
    EvidenceContext,
    EvidenceItem,
    EvidenceRequest,
    EvidenceSufficiency,
    FetchResponse,
    FetchedSource,
    ResearchIndexResult,
    SearchHit,
    SearchResponse,
)
from app.research.indexing import index_research_sources
from app.research.research_job_stages import collect_evidence_for_job
from app.research.retrieval import retrieve_evidence
from app.research.turn_evidence import load_evidence_text_for_turn
from app.research.web_research import expand_evidence_via_web_search

pytestmark = pytest.mark.unit


def _evidence(*, items: bool, sufficient: bool) -> EvidenceContext:
    evidence_items = []
    if items:
        evidence_items = [
            EvidenceItem(
                chunk_id="c1",
                source_id="s1",
                excerpt="본문",
                score=0.9,
                title="t",
                url="https://example.com",
            )
        ]
    return EvidenceContext(
        items=evidence_items,
        sufficiency=EvidenceSufficiency(
            sufficient=sufficient,
            supporting_chunk_ids=[i.chunk_id for i in evidence_items],
            reason_code="matched_chunks" if sufficient else "no_matching_chunks",
        ),
        is_grounded=sufficient,
        warning_code=None if sufficient else "insufficient_evidence",
    )


def test_retrieve_evidence_logs_hit_summary(tmp_path, caplog):
    from app.research.evidence_index import ResearchEvidenceIndex

    evidence_index = ResearchEvidenceIndex(
        tmp_path / "chroma_db",
        embedding_model="test-model",
        embedding_dimension=3,
        chunk_schema_version="test-schema",
    )
    evidence_index.store_source_chunks(
        scope="public",
        ids=["chunk-1"],
        documents=["관련 본문"],
        embeddings=[[1.0, 0.0, 0.0]],
        metadatas=[
            {
                "chunk_id": "chunk-1",
                "source_id": str(uuid4()),
                "canonical_url": "https://example.com",
                "source_url": "https://example.com",
                "title": "Example",
                "language": "ko",
            }
        ],
    )

    with caplog.at_level(logging.INFO, logger="app.research.retrieval"):
        result = retrieve_evidence(
            EvidenceRequest(
                user_id=uuid4(),
                manuscript_id=uuid4(),
                query="관련",
                limit=3,
            ),
            evidence_index=evidence_index,
            query_embedding=[1.0, 0.0, 0.0],
        )

    assert result.sufficiency.sufficient is True
    assert any(
        "research.evidence_retrieved" in record.message
        and "'hit_count': 1" in record.message
        and "'sufficient': True" in record.message
        and "'reason_code': 'matched_chunks'" in record.message
        for record in caplog.records
    )


@pytest.mark.asyncio
async def test_expand_evidence_logs_search_fetch_and_index_request(monkeypatch, caplog):
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
        fetched_at=MagicMock(),
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

    with caplog.at_level(logging.INFO, logger="app.research.web_research"):
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

    messages = [record.message for record in caplog.records]
    assert any(
        "research.web_search_completed" in message and "'hit_count': 1" in message
        for message in messages
    )
    assert any("research.fetch_succeeded" in message for message in messages)
    assert any(
        "research.index_sources_requested" in message
        and "'source_count': 1" in message
        for message in messages
    )


@pytest.mark.asyncio
async def test_collect_evidence_logs_stage_boundaries(monkeypatch, caplog):
    job = ResearchJob(
        user_id=uuid4(),
        manuscript_id=uuid4(),
        claim_or_query="테스트 주장",
    )
    job.id = uuid4()
    insufficient = _evidence(items=False, sufficient=False)
    sufficient = _evidence(items=True, sufficient=True)
    retrieve = MagicMock(side_effect=[insufficient, sufficient])
    monkeypatch.setattr(
        "app.research.research_job_stages.retrieve_evidence",
        retrieve,
    )
    web_research = AsyncMock(return_value=None)

    with caplog.at_level(logging.INFO, logger="app.research.research_job_stages"):
        result = await collect_evidence_for_job(
            db=object(),
            job=job,
            query="테스트",
            evidence_index=object(),
            embed_query=lambda _query: [0.1, 0.2],
            web_research=web_research,
        )

    assert result.evidence.sufficiency.sufficient is True
    messages = [record.message for record in caplog.records]
    assert any("research.evidence_collection.start" in message for message in messages)
    assert any(
        "research.evidence_collection.initial_retrieve" in message
        and "'sufficient': False" in message
        for message in messages
    )
    assert any(
        "research.evidence_collection.web_expand.start" in message for message in messages
    )
    assert any(
        "research.evidence_collection.reretrieve" in message
        and "'sufficient': True" in message
        for message in messages
    )


def test_load_evidence_text_for_turn_logs_injection_summary(monkeypatch, caplog):
    evidence = _evidence(items=True, sufficient=True)
    monkeypatch.setattr(
        "app.research.turn_evidence.create_research_embeddings",
        lambda: MagicMock(embed_query=lambda _query: [0.1, 0.2]),
    )
    monkeypatch.setattr(
        "app.research.turn_evidence.create_research_evidence_index",
        lambda: object(),
    )
    monkeypatch.setattr(
        "app.research.turn_evidence.retrieve_evidence",
        lambda *args, **kwargs: evidence,
    )
    monkeypatch.setattr(
        "app.research.turn_evidence.format_evidence_system_text",
        lambda _evidence: "formatted",
    )

    with caplog.at_level(logging.INFO, logger="app.research.turn_evidence"):
        text = load_evidence_text_for_turn(
            user_id=uuid4(),
            manuscript_id=uuid4(),
            query="테스트",
        )

    assert text == "formatted"
    assert any(
        "research.turn_evidence_injected" in record.message
        and "'item_count': 1" in record.message
        and "'top_scores': [0.9]" in record.message
        for record in caplog.records
    )


@pytest.mark.asyncio
async def test_index_research_sources_logs_completion(
    db_session, tmp_path, monkeypatch, caplog
):
    from app.models.manuscript import ConceptType, Manuscript
    from app.models.user import User
    from app.research.contracts import ResearchIndexRequest
    from app.research.evidence_index import ResearchEvidenceIndex
    from langchain_core.embeddings import DeterministicFakeEmbedding
    from app.services.storage.local import LocalFileStorage
    from datetime import datetime, timezone
    from app.research.contracts import ExtractedSection

    user = User(login_id="log-user", password_hash="hash", nickname="log")
    db_session.add(user)
    db_session.flush()
    manuscript = Manuscript(
        user_id=user.id,
        topic="로그",
        concept=ConceptType.TECH_DEEPDIVE,
    )
    db_session.add(manuscript)
    db_session.flush()
    job = ResearchJob(user_id=user.id, manuscript_id=manuscript.id)
    db_session.add(job)
    db_session.commit()

    fetched = FetchedSource(
        requested_url="https://example.com/log",
        canonical_url="https://example.com/log",
        title="로그 테스트",
        publisher="Example",
        published_at="2026-07-01",
        text="충분히 긴 본문입니다. " * 30,
        sections=[
            ExtractedSection(
                kind="comment",
                text="추가 설명",
                permalink="https://example.com/log#comment-1",
            )
        ],
        media_type="text/html",
        fetched_at=datetime.now(timezone.utc),
        content_hash="hash",
        source_key="source-key",
    )

    with caplog.at_level(logging.INFO, logger="app.research.indexing"):
        result = await index_research_sources(
            ResearchIndexRequest(
                research_job_id=job.id,
                user_id=user.id,
                manuscript_id=manuscript.id,
                sources=[fetched],
            ),
            db=db_session,
            storage=LocalFileStorage(tmp_path / "storage"),
            embeddings=DeterministicFakeEmbedding(size=8),
            evidence_index=ResearchEvidenceIndex(
                tmp_path / "chroma_db",
                embedding_model="test-model",
                embedding_dimension=8,
                chunk_schema_version="chunk-600-100-v1",
            ),
            admit_source=lambda _source: "public",
        )

    assert result.status == "completed"
    assert any(
        "research.index_completed" in record.message
        and "'chunk_count':" in record.message
        and "'embedding_model': 'test-model'" in record.message
        and "'embedding_dimension': 8" in record.message
        for record in caplog.records
    )
