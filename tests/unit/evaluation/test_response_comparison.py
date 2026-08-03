import pytest

from app.evaluation.response_comparison_contracts import GeneratedResponse, PairwiseJudgment
from app.evaluation.response_comparison import (
    build_comparison_prompt,
    combine_order_swapped_judgments,
    parse_comparison_judgment,
)

pytestmark = pytest.mark.unit


def test_parse_comparison_judgment_reads_winners_and_reason():
    raw = """{
      "specificity_winner": "B",
      "naturalness_winner": "tie",
      "accuracy_winner": "A",
      "overall_winner": "B",
      "reason": "B가 더 구체적이다."
    }"""

    parsed = parse_comparison_judgment(raw)

    assert parsed["specificity_winner"] == "B"
    assert parsed["naturalness_winner"] == "tie"
    assert parsed["accuracy_winner"] == "A"
    assert parsed["overall_winner"] == "B"
    assert "구체적" in parsed["reason"]


def test_combine_order_swapped_judgments_maps_labels_and_detects_flip():
    first = {
        "specificity_winner": "B",
        "naturalness_winner": "A",
        "accuracy_winner": "B",
        "overall_winner": "B",
        "reason": "근거 답이 낫다.",
    }
    second_consistent = {
        "specificity_winner": "A",
        "naturalness_winner": "B",
        "accuracy_winner": "A",
        "overall_winner": "A",
        "reason": "근거 답이 낫다.",
    }
    second_flipped = {
        "specificity_winner": "B",
        "naturalness_winner": "A",
        "accuracy_winner": "B",
        "overall_winner": "B",
        "reason": "이번엔 반대.",
    }

    consistent = combine_order_swapped_judgments(first, second_consistent)
    flipped = combine_order_swapped_judgments(first, second_flipped)

    assert consistent == PairwiseJudgment(
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

    assert "수치가 맞나요?" in prompt
    assert "95%라고 들었어요." in prompt
    assert "잘 모르겠어요." in prompt
    assert "92%입니다." in prompt
    assert "Answer A" in prompt
    assert "Answer B" in prompt
