import pytest

from app.evaluation.absolute_judgment import (
    build_absolute_judgment_prompt,
    parse_absolute_judgment,
)

pytestmark = pytest.mark.unit


def test_absolute_judgment_prompt_prioritizes_reference_suggestion():
    prompt = build_absolute_judgment_prompt(
        claim="RAG를 사용하면 LLM 응답의 품질이 좋아진다.",
        topic="RAG와 응답 품질",
        phase="say",
        response_body="맞아요, RAG는 보통 도움이 됩니다.",
    )
    assert "정답" in prompt
    assert "참고자료" in prompt or "reference_suggestion" in prompt
    assert "근거" in prompt
    assert "reference_suggestion" in prompt
    assert "knowledge_depth" in prompt
    assert "연속" in prompt or "인위적인 등급" in prompt
    assert "41~60" not in prompt and "점수 밴드" not in prompt
    assert "reference_suggestion" in prompt
    assert "knowledge_depth" in prompt
    assert "주입된 근거" not in prompt


def test_parse_absolute_judgment():
    judgment = parse_absolute_judgment(
        """
        {
          "reference_suggestion": 15,
          "claim_sharpening": 30,
          "knowledge_depth": 25,
          "dialogue_fit": 55,
          "next_step_clarity": 20,
          "overall": 22,
          "reason": "상투적 동의만 있고 확인할 참고자료·검증 경로가 없음."
        }
        """
    )
    assert judgment.scores.overall == 22
    assert judgment.scores.reference_suggestion == 15
    assert "참고" in judgment.reason or "검증" in judgment.reason


def test_parse_absolute_judgment_rejects_out_of_range():
    with pytest.raises(ValueError):
        parse_absolute_judgment(
            '{"reference_suggestion":101,"claim_sharpening":50,"knowledge_depth":50,'
            '"dialogue_fit":50,"next_step_clarity":50,"overall":50,"reason":"x"}'
        )
