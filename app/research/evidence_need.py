import re
from dataclasses import dataclass

_NUMERIC_PATTERN = re.compile(
    r"(\d+\s*%|\d+\s*(ms|초|분|시간|시간대|배|건|회)|p\d{2}|\b\d{2,}\b)",
    re.IGNORECASE,
)
_FACTUAL_HINTS = (
    "벤치마크",
    "공식",
    "timeout",
    "latency",
    "정확도",
    "hit rate",
    "SLA",
    "기본값",
    "문서에",
    "보고서에",
)


@dataclass(frozen=True)
class EvidenceNeedDecision:
    required: bool
    claim_or_query: str | None
    reason_code: str
    confidence: float


def detect_evidence_need(user_message: str) -> EvidenceNeedDecision:
    """조사 필요 여부를 최소 휴리스틱으로 판단한다. UserAction과 분리된다."""
    text = user_message.strip()
    if not text:
        return EvidenceNeedDecision(
            required=False,
            claim_or_query=None,
            reason_code="empty_message",
            confidence=1.0,
        )

    has_number = bool(_NUMERIC_PATTERN.search(text))
    has_hint = any(hint.lower() in text.lower() for hint in _FACTUAL_HINTS)
    if has_number or has_hint:
        return EvidenceNeedDecision(
            required=True,
            claim_or_query=text,
            reason_code="numeric_or_factual_claim",
            confidence=0.7 if has_number and has_hint else 0.55,
        )
    return EvidenceNeedDecision(
        required=False,
        claim_or_query=None,
        reason_code="no_research_signal",
        confidence=0.6,
    )
