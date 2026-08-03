import json
from uuid import uuid4

import pytest

from app.research.contracts import EvidenceContext, EvidenceItem, EvidenceSufficiency
from app.research.prepared_evidence import (
    format_prepared_evidence_system_text,
    serialize_evidence_context,
)

pytestmark = pytest.mark.unit


def test_serialize_and_format_prepared_evidence_for_next_turn():
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

    payload = serialize_evidence_context(evidence)
    text = format_prepared_evidence_system_text(payload)

    assert "신뢰하지 않은 참고 자료" in text
    assert "https://docs.example/timeout" in text
    assert "360분" in text
    assert json.loads(payload)["items"][0]["chunk_id"] == "chunk-a"
