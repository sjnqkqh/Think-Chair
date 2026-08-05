from types import SimpleNamespace
from unittest.mock import MagicMock
from uuid import uuid4

import pytest

import app.research.research_job_stages as stages_module
from app.models.research import ResearchJobStatus
from app.research.contracts import (
    EvidenceContext,
    EvidenceItem,
    EvidenceSufficiency,
)
from app.research.research_job_stages import (
    EvidenceCollectionResult,
    collect_evidence_for_job,
    decide_job_outcome,
)

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
            reason_code="matched_chunks" if items else "no_matching_chunks",
        ),
        is_grounded=sufficient,
        warning_code=None if sufficient else "insufficient_evidence",
    )


def test_decide_job_outcome_completed_when_sufficient():
    decision = decide_job_outcome(
        EvidenceCollectionResult(evidence=_evidence(items=True, sufficient=True)),
    )
    assert decision.status == ResearchJobStatus.COMPLETED
    assert decision.terminal_error is None


def test_decide_job_outcome_partial_when_items_but_not_sufficient():
    decision = decide_job_outcome(
        EvidenceCollectionResult(evidence=_evidence(items=True, sufficient=False)),
    )
    assert decision.status == ResearchJobStatus.PARTIAL


def test_decide_job_outcome_failed_uses_web_error():
    decision = decide_job_outcome(
        EvidenceCollectionResult(
            evidence=_evidence(items=False, sufficient=False),
            web_error="search_not_configured",
        ),
    )
    assert decision.status == ResearchJobStatus.FAILED
    assert decision.terminal_error == "search_not_configured"


class _FakeEvidenceIndex:
    """web_research가 인덱싱한 것처럼 chunks 목록을 직접 채워 넣는 fake."""

    def __init__(self):
        self.chunks: list[dict] = []

    def query_chunks(self, *, scope, query_embedding, limit, where=None):
        return list(self.chunks) if scope == "public" else []


def _relevant_hit(chunk_id: str, url: str) -> dict:
    return {
        "id": chunk_id,
        "document": "본문",
        "metadata": {"chunk_id": chunk_id, "canonical_url": url, "source_id": chunk_id},
        "distance": 0.0,
    }


def _fake_job():
    return SimpleNamespace(id=uuid4(), user_id=uuid4(), manuscript_id=uuid4())


async def test_collect_evidence_for_job_stops_once_sufficient():
    evidence_index = _FakeEvidenceIndex()
    round_count = 0

    async def web_research(**_kwargs):
        nonlocal round_count
        round_count += 1
        evidence_index.chunks.append(
            _relevant_hit(f"c{round_count}", f"https://example/{round_count}")
        )
        return None

    result = await collect_evidence_for_job(
        MagicMock(),
        _fake_job(),
        query="q",
        evidence_index=evidence_index,
        embed_query=lambda _q: [0.0],
        web_research=web_research,
    )

    assert result.evidence.sufficiency.sufficient is True
    assert round_count == 3


async def test_collect_evidence_for_job_stops_early_without_progress():
    evidence_index = _FakeEvidenceIndex()
    evidence_index.chunks = [_relevant_hit("c1", "https://example/1")]
    round_count = 0

    async def web_research(**_kwargs):
        nonlocal round_count
        round_count += 1
        return "search_empty"

    result = await collect_evidence_for_job(
        MagicMock(),
        _fake_job(),
        query="q",
        evidence_index=evidence_index,
        embed_query=lambda _q: [0.0],
        web_research=web_research,
    )

    assert result.evidence.sufficiency.sufficient is False
    assert result.web_error == "search_empty"
    assert round_count == 1


async def test_collect_evidence_for_job_caps_at_max_expand_rounds(monkeypatch):
    monkeypatch.setattr(stages_module, "MAX_WEB_EXPAND_ROUNDS", 2)
    evidence_index = _FakeEvidenceIndex()
    round_count = 0

    async def web_research(**_kwargs):
        nonlocal round_count
        round_count += 1
        evidence_index.chunks.append(
            _relevant_hit(f"c{round_count}", f"https://example/{round_count}")
        )
        return None

    result = await collect_evidence_for_job(
        MagicMock(),
        _fake_job(),
        query="q",
        evidence_index=evidence_index,
        embed_query=lambda _q: [0.0],
        web_research=web_research,
    )

    # 매 라운드 새 관련 URL을 모았지만(진행됨) 3개 상한(MIN_DISTINCT_RELEVANT_URLS)에는
    # 못 미친 채로, 라운드 상한(2)에서 멈춘다.
    assert round_count == 2
    assert result.evidence.sufficiency.sufficient is False
