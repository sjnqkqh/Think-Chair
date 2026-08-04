import json

import pytest

from app.evaluation.response_comparison_contracts import PreparedEvidence, ResponseComparisonCase
from app.evaluation.case_response_comparison import compare_case_responses

pytestmark = pytest.mark.unit


def test_compare_case_responses_runs_citation_check_and_judgment_with_injected_models():
    case = ResponseComparisonCase(
        case_id="case-1",
        ai_question="수치가 맞나요?",
        human_response="95%라고 들었어요.",
        allowed_source_keys=("src-a",),
        forbidden_source_keys=(),
        prepared_evidence=(
            PreparedEvidence(
                source_key="src-a",
                url="https://example.com/a",
                title="공식",
                text="정확도 92%",
            ),
        ),
    )
    generate_calls = {"n": 0}

    def generate_invoke(prompt: str) -> str:
        generate_calls["n"] += 1
        if "준비된 근거" in prompt:
            return json.dumps(
                {
                    "body": (
                        "공개 자료 기준 92%입니다. "
                        "https://example.com/a"
                    ),
                    "cited_source_keys": ["src-a"],
                    "cited_urls": ["https://example.com/a"],
                },
                ensure_ascii=False,
            )
        return json.dumps(
            {
                "body": "정확한 수치는 자료 확인이 필요합니다. 어디서 95%를 보셨나요?",
                "cited_source_keys": [],
                "cited_urls": [],
            },
            ensure_ascii=False,
        )

    def judge_invoke(prompt: str) -> str:
        answer_a = prompt.split("[Answer A]", 1)[1].split("[Answer B]", 1)[0]
        grounded_is_a = "공개 자료 기준 92%입니다." in answer_a
        high, low = (90, 55) if grounded_is_a else (55, 90)
        return json.dumps(
            {
                "specificity": {"A": high, "B": low},
                "naturalness": {"A": 80, "B": 80},
                "accuracy": {"A": high, "B": low},
                "overall": {"A": high, "B": low},
                "reason": "근거 답이 더 구체적이다.",
            },
            ensure_ascii=False,
        )

    result = compare_case_responses(
        case,
        generate_invoke=generate_invoke,
        judge_invoke=judge_invoke,
    )

    assert generate_calls["n"] == 2
    assert result.ai_question == "수치가 맞나요?"
    assert result.human_response == "95%라고 들었어요."
    assert result.prepared_evidence[0].source_key == "src-a"
    assert "정확도 92%" in result.prepared_evidence[0].text
    assert result.baseline_citation_check.passed is True
    assert result.grounded_citation_check.passed is True
    assert result.judgment is not None
    assert result.judgment.overall_winner == "grounded"
    assert result.judgment.order_flipped is False
