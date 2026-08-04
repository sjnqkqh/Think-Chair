import pytest

from app.models.research import ResearchJobStatus
from app.research.contracts import (
    EvidenceContext,
    EvidenceItem,
    EvidenceSufficiency,
    GroundedResponseResult,
)
from app.evaluation.response_comparison_contracts import GeneratedResponse
from app.research.research_job_stages import (
    EvidenceCollectionResult,
    EvaluationResult,
    ResponsePairResult,
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


def _evaluation(*, grounded: bool) -> EvaluationResult:
    return EvaluationResult(
        responses=ResponsePairResult(
            baseline=GeneratedResponse(body="baseline"),
            grounded=GroundedResponseResult(
                text="grounded",
                citations=[],
                is_grounded=grounded,
                warning_code=None if grounded else "invalid_citation_fallback",
            ),
        )
    )


def test_decide_job_outcome_completed_when_sufficient_and_grounded():
    decision = decide_job_outcome(
        EvidenceCollectionResult(evidence=_evidence(items=True, sufficient=True)),
        _evaluation(grounded=True),
    )
    assert decision.status == ResearchJobStatus.COMPLETED
    assert decision.terminal_error is None
    assert decision.prepared_evidence_json


def test_decide_job_outcome_partial_when_items_but_not_fully_grounded():
    decision = decide_job_outcome(
        EvidenceCollectionResult(evidence=_evidence(items=True, sufficient=False)),
        _evaluation(grounded=False),
    )
    assert decision.status == ResearchJobStatus.PARTIAL
    assert decision.prepared_evidence_json


def test_decide_job_outcome_failed_uses_web_error():
    decision = decide_job_outcome(
        EvidenceCollectionResult(
            evidence=_evidence(items=False, sufficient=False),
            web_error="search_not_configured",
        ),
        _evaluation(grounded=False),
    )
    assert decision.status == ResearchJobStatus.FAILED
    assert decision.terminal_error == "search_not_configured"
    assert decision.prepared_evidence_json is None
