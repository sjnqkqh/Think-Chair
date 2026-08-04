import re
from dataclasses import dataclass

# 한글 접미 단위는 \b 경계가 깨지므로 명시적으로 포함한다.
_NUMERIC_PATTERN = re.compile(
    r"("
    r"\d+\s*%"
    r"|\d+\s*(ms|초|분|시간|시간대|배|건|회|비트|토큰|token|gb|mb|kb)"
    r"|p\d{2}"
    r"|\b\d{2,}\b"
    r")",
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
_GENERALIZATION_MARKERS = (
    "보통",
    "일반적으로",
    "일반적",
    "대략",
    "흔히",
    "대체로",
    "대부분",
    "전형적으로",
    "모범",
    "권장",
)
_EVIDENCE_WORTHY_TOPICS = (
    "cpu",
    "memory",
    "메모리",
    "점유율",
    "오토 스케일",
    "오토스케일",
    "스케일링",
    "양자화",
    "성능",
    "캐시",
    "hit rate",
    "커넥션",
    "connection",
    "커넥션 풀",
    "connection pool",
    "풀 크기",
    "pool size",
    "청크",
    "chunk",
    "토큰",
    "token",
    "워커",
    "worker",
    "latency",
    "timeout",
    "throughput",
    "벤치마크",
    "redis",
    "postgres",
    "nginx",
    "rag",
)


@dataclass(frozen=True)
class EvidenceNeedDecision:
    required: bool
    claim_or_query: str | None
    reason_code: str
    confidence: float


def detect_evidence_need(user_message: str) -> EvidenceNeedDecision:
    """조사 필요 여부를 최소 휴리스틱으로 판단한다. UserAction과 분리된다.

    수치·사실 신호뿐 아니라, 일반론/모범 사례 주장(근거로 보강할 가치가 있는
    기술 주제)도 조사 대상으로 본다.
    """
    text = user_message.strip()
    if not text:
        return EvidenceNeedDecision(
            required=False,
            claim_or_query=None,
            reason_code="empty_message",
            confidence=1.0,
        )

    lowered = text.lower()
    has_number = bool(_NUMERIC_PATTERN.search(text))
    has_hint = any(hint.lower() in lowered for hint in _FACTUAL_HINTS)
    if has_number or has_hint:
        return EvidenceNeedDecision(
            required=True,
            claim_or_query=text,
            reason_code="numeric_or_factual_claim",
            confidence=0.7 if has_number and has_hint else 0.55,
        )

    has_generalization = any(marker in text for marker in _GENERALIZATION_MARKERS)
    has_topic = any(topic in lowered for topic in _EVIDENCE_WORTHY_TOPICS)
    if has_generalization and has_topic:
        return EvidenceNeedDecision(
            required=True,
            claim_or_query=text,
            reason_code="general_practice_claim",
            confidence=0.6,
        )

    return EvidenceNeedDecision(
        required=False,
        claim_or_query=None,
        reason_code="no_research_signal",
        confidence=0.6,
    )
