import pytest

from app.evaluation.absolute_judgment import (
    build_absolute_judgment_prompt,
    parse_absolute_judgment,
)

pytestmark = pytest.mark.unit


def test_absolute_judgment_prompt_is_strict():
    prompt = build_absolute_judgment_prompt(
        claim="RAG를 사용하면 LLM 응답의 품질이 좋아진다.",
        topic="RAG와 응답 품질",
        phase="say",
        response_body="맞아요, RAG는 보통 도움이 됩니다.",
        evidence_text="",
    )
    assert "엄격" in prompt or "깐깐" in prompt or "관대" in prompt
    assert "40~60" in prompt or "40-60" in prompt
    assert "specificity" in prompt
    assert "RAG를 사용하면 LLM 응답의 품질이 좋아진다." in prompt
    assert "맞아요, RAG는 보통 도움이 됩니다." in prompt


def test_parse_absolute_judgment():
    judgment = parse_absolute_judgment(
        """
        {
          "specificity": 38,
          "naturalness": 52,
          "accuracy": 35,
          "overall": 40,
          "reason": "수치·한계·출처 없이 일반론만 반복함."
        }
        """
    )
    assert judgment.scores.overall == 40
    assert "일반론" in judgment.reason


def test_parse_absolute_judgment_rejects_out_of_range():
    with pytest.raises(ValueError):
        parse_absolute_judgment(
            '{"specificity":101,"naturalness":50,"accuracy":50,"overall":50,"reason":"x"}'
        )
