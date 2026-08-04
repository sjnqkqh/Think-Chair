import pytest

from app.research.evidence_need import detect_evidence_need

pytestmark = pytest.mark.unit


GENERAL_CLAIMS = [
    (
        "autoscaling_cpu_memory",
        "오토 스케일링 시, 보통 CPU 점유율이나 Memory 점유율을 기준으로 "
        "서버 증감을 수행합니다.",
    ),
    (
        "four_bit_quantization",
        "일반적으로 4비트 양자화까지는 성능이 크게 떨어지지 않습니다.",
    ),
    (
        "redis_cache_hit_rate",
        "보통 Redis 캐시 hit rate가 90% 이상이면 캐시 계층이 잘 동작한다고 봅니다.",
    ),
    (
        "connection_pool_size",
        "웹 서비스에서는 보통 워커당 DB 커넥션 풀 크기를 작게 유지하는 편이 "
        "안전합니다.",
    ),
    (
        "rag_chunk_size",
        "RAG에서는 청크를 대략 500토큰 전후로 나누는 게 일반적입니다.",
    ),
]


def test_detect_evidence_need_flags_numeric_claims():
    decision = detect_evidence_need(
        "GitHub Actions 기본 job timeout이 60분이라서 자주 잘리는 것 같습니다."
    )

    assert decision.required is True
    assert decision.claim_or_query
    assert decision.reason_code == "numeric_or_factual_claim"


def test_detect_evidence_need_skips_light_acknowledgement():
    decision = detect_evidence_need("네, 그 방향으로 이어서 정리해 볼게요.")

    assert decision.required is False
    assert decision.claim_or_query is None
    assert decision.reason_code == "no_research_signal"


def test_detect_evidence_need_skips_ordinary_planning_without_claim():
    decision = detect_evidence_need("오늘은 아웃라인부터 잡고 문단을 나눠 볼게요.")

    assert decision.required is False
    assert decision.reason_code == "no_research_signal"


def test_detect_evidence_need_skips_general_word_without_technical_topic():
    decision = detect_evidence_need("보통 이 문제를 풀면 다음으로 넘어갈 수 있습니다.")

    assert decision.required is False
    assert decision.reason_code == "no_research_signal"


@pytest.mark.parametrize(
    ("case_id", "claim"),
    GENERAL_CLAIMS,
    ids=[case_id for case_id, _ in GENERAL_CLAIMS],
)
def test_detect_evidence_need_flags_general_practice_claims(case_id, claim):
    decision = detect_evidence_need(claim)

    assert decision.required is True, case_id
    assert decision.claim_or_query == claim
    assert decision.reason_code in {
        "numeric_or_factual_claim",
        "general_practice_claim",
    }
