import pytest

from app.research.contracts import EvidenceContext, EvidenceItem, EvidenceSufficiency
from app.research.prepared_evidence import format_evidence_system_text

pytestmark = pytest.mark.unit


def test_format_evidence_system_text():
    evidence = EvidenceContext(
        items=[
            EvidenceItem(
                chunk_id="chunk-a",
                source_id="src-a",
                excerpt="기본 timeout은 360분이다.",
                score=0.9,
                title="Timeout",
                url="https://docs.example/timeout",
            )
        ],
        sufficiency=EvidenceSufficiency(
            sufficient=True,
            supporting_chunk_ids=["chunk-a"],
            reason_code="matched_chunks",
        ),
        is_grounded=True,
    )

    text = format_evidence_system_text(evidence)

    assert "신뢰하지 않은 참고 자료" in text
    assert "https://docs.example/timeout" in text
    assert "360분" in text


def test_format_evidence_system_text_empty():
    evidence = EvidenceContext(
        items=[],
        sufficiency=EvidenceSufficiency(
            sufficient=False,
            reason_code="no_matching_chunks",
        ),
        is_grounded=False,
        warning_code="insufficient_evidence",
    )
    assert format_evidence_system_text(evidence) == ""
