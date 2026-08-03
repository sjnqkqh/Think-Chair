import json

import pytest

from app.research.contracts import (
    EvidenceContext,
    EvidenceItem,
    EvidenceSufficiency,
    GroundedResponseRequest,
)
from app.research.grounded_response import generate_grounded_response

pytestmark = pytest.mark.unit


def _evidence() -> EvidenceContext:
    return EvidenceContext(
        items=[
            EvidenceItem(
                chunk_id="chunk-a",
                source_id="src-a",
                excerpt="기본 timeout은 360분이다.",
                score=0.9,
                title="Timeout",
                url="https://docs.example/timeout",
            ),
        ],
        sufficiency=EvidenceSufficiency(
            sufficient=True,
            supporting_chunk_ids=["chunk-a"],
            reason_code="matched_chunks",
        ),
        is_grounded=True,
    )


def test_generate_grounded_response_keeps_only_evidence_citations():
    calls = {"n": 0}

    def invoke(prompt: str) -> str:
        calls["n"] += 1
        return json.dumps(
            {
                "body": (
                    "기본 timeout은 360분입니다. "
                    "https://docs.example/timeout"
                ),
                "citations": [
                    {
                        "source_id": "src-a",
                        "chunk_id": "chunk-a",
                        "url": "https://docs.example/timeout",
                    }
                ],
            },
            ensure_ascii=False,
        )

    result = generate_grounded_response(
        GroundedResponseRequest(
            phase="say",
            conversation_context="사용자: 타임아웃이 60분이라고 했습니다.",
            evidence=_evidence(),
        ),
        invoke=invoke,
    )

    assert calls["n"] == 1
    assert result.is_grounded is True
    assert result.citations[0].chunk_id == "chunk-a"
    assert "https://docs.example/timeout" in result.text


def test_generate_grounded_response_retries_once_then_falls_back_on_ghost_citation():
    calls = {"n": 0}

    def invoke(prompt: str) -> str:
        calls["n"] += 1
        if calls["n"] == 1:
            return json.dumps(
                {
                    "body": "유령 출처를 씁니다. https://ghost.example/x",
                    "citations": [
                        {
                            "source_id": "ghost",
                            "chunk_id": "ghost-chunk",
                            "url": "https://ghost.example/x",
                        }
                    ],
                },
                ensure_ascii=False,
            )
        return json.dumps(
            {
                "body": "여전히 유령입니다. https://ghost.example/x",
                "citations": [
                    {
                        "source_id": "ghost",
                        "chunk_id": "ghost-chunk",
                        "url": "https://ghost.example/x",
                    }
                ],
            },
            ensure_ascii=False,
        )

    result = generate_grounded_response(
        GroundedResponseRequest(
            phase="say",
            conversation_context="사용자: 수치를 확인합니다.",
            evidence=_evidence(),
        ),
        invoke=invoke,
    )

    assert calls["n"] == 2
    assert result.is_grounded is False
    assert result.citations == []
    assert result.warning_code == "invalid_citation_fallback"


def test_generate_grounded_response_without_evidence_does_not_fabricate():
    def invoke(prompt: str) -> str:
        return json.dumps(
            {
                "body": "지금은 확인 질문만 이어가겠습니다.",
                "citations": [
                    {
                        "source_id": "made-up",
                        "chunk_id": "made-up",
                        "url": "https://made-up.example",
                    }
                ],
            },
            ensure_ascii=False,
        )

    result = generate_grounded_response(
        GroundedResponseRequest(
            phase="say",
            conversation_context="사용자: 잘 모르겠습니다.",
            evidence=EvidenceContext(
                items=[],
                sufficiency=EvidenceSufficiency(
                    sufficient=False,
                    missing_aspects=["supporting_evidence"],
                    reason_code="no_matching_chunks",
                ),
                is_grounded=False,
                warning_code="insufficient_evidence",
            ),
        ),
        invoke=invoke,
    )

    assert result.is_grounded is False
    assert result.citations == []
