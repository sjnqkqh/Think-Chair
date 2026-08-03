import pytest

from app.research.evidence_need import detect_evidence_need

pytestmark = pytest.mark.unit


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
