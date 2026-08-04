import pytest

from app.models.research import ResearchJobStatus
from app.research.contracts import (
    EvidenceContext,
    EvidenceItem,
    EvidenceSufficiency,
)
from app.research.research_job_stages import (
    EvidenceCollectionResult,
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
