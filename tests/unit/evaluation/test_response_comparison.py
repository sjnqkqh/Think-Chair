import pytest

from app.evaluation.response_comparison_contracts import (
    AnswerScores,
    GeneratedResponse,
    PairwiseJudgment,
)
from app.evaluation.response_comparison import (
    build_comparison_prompt,
    combine_order_swapped_judgments,
    parse_comparison_judgment,
)

pytestmark = pytest.mark.unit


def test_parse_comparison_judgment_reads_scores_and_reason():
    raw = """{
      "specificity": {"A": 55, "B": 88},
      "naturalness": {"A": 80, "B": 80},
      "accuracy": {"A": 70, "B": 60},
      "overall": {"A": 65, "B": 82},
      "reason": "B가 더 구체적이다."
    }"""

    parsed = parse_comparison_judgment(raw)

    assert parsed["specificity"] == {"A": 55, "B": 88}
    assert parsed["naturalness"] == {"A": 80, "B": 80}
    assert parsed["accuracy"] == {"A": 70, "B": 60}
    assert parsed["overall"] == {"A": 65, "B": 82}
    assert "구체적" in parsed["reason"]


def test_parse_comparison_judgment_rejects_out_of_range_score():
    with pytest.raises(ValueError, match="0..100"):
        parse_comparison_judgment(
            '{"specificity":{"A":101,"B":50},"naturalness":{"A":50,"B":50},'
            '"accuracy":{"A":50,"B":50},"overall":{"A":50,"B":50},"reason":"x"}'
        )


def test_combine_order_swapped_judgments_averages_scores_and_detects_flip():
    first = {
        "specificity": {"A": 40, "B": 90},
        "naturalness": {"A": 80, "B": 60},
        "accuracy": {"A": 50, "B": 80},
        "overall": {"A": 50, "B": 85},
        "reason": "근거 답이 낫다.",
    }
    second_consistent = {
        "specificity": {"A": 88, "B": 42},
        "naturalness": {"A": 58, "B": 78},
        "accuracy": {"A": 82, "B": 48},
        "overall": {"A": 84, "B": 52},
        "reason": "근거 답이 낫다.",
    }
    second_flipped = {
        "specificity": {"A": 40, "B": 90},
        "naturalness": {"A": 60, "B": 80},
        "accuracy": {"A": 50, "B": 80},
        "overall": {"A": 50, "B": 85},
        "reason": "이번엔 반대.",
    }

    consistent = combine_order_swapped_judgments(first, second_consistent)
    flipped = combine_order_swapped_judgments(first, second_flipped)

    assert consistent == PairwiseJudgment(
        baseline_scores=AnswerScores(
            specificity=41, naturalness=79, accuracy=49, overall=51
        ),
        grounded_scores=AnswerScores(
            specificity=89, naturalness=59, accuracy=81, overall=84
        ),
        specificity_winner="grounded",
        naturalness_winner="baseline",
        accuracy_winner="grounded",
        overall_winner="grounded",
        reason="근거 답이 낫다.",
        order_flipped=False,
    )
    assert flipped.overall_winner == "tie"
    assert flipped.order_flipped is True


def test_build_comparison_prompt_includes_both_answers_without_system_labels():
    prompt = build_comparison_prompt(
        ai_question="수치가 맞나요?",
        human_response="95%라고 들었어요.",
        answer_a=GeneratedResponse(
            body="잘 모르겠어요. 근거가 있나요?",
            cited_source_keys=(),
            cited_urls=(),
        ),
        answer_b=GeneratedResponse(
            body="공개 자료 기준으로는 92%입니다.",
            cited_source_keys=("src-a",),
            cited_urls=(),
        ),
    )

    assert "100점 만점" in prompt
    assert "수치가 맞나요?" in prompt
    assert "95%라고 들었어요." in prompt
    assert "잘 모르겠어요." in prompt
    assert "92%입니다." in prompt
    assert "Answer A" in prompt
    assert "Answer B" in prompt
