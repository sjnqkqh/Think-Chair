import pytest
from pydantic import ValidationError

from app.evaluation.contracts import (
    CaseComparisonResult,
    CitationCheckResult,
    ComparisonSummary,
    GeneratedResponse,
    PairwiseJudgment,
    PreparedEvidence,
    ResponseComparisonCase,
)

pytestmark = pytest.mark.unit


def test_response_comparison_case_requires_dialogue_and_evidence_lists():
    case = ResponseComparisonCase.model_validate(
        {
            "case_id": "case-1",
            "ai_question": "그 수치가 맞나요?",
            "human_response": "정확도 95%라고 들었어요.",
            "allowed_source_keys": ["src-a"],
            "forbidden_source_keys": ["src-private"],
            "prepared_evidence": [
                {
                    "source_key": "src-a",
                    "url": "https://example.com/a",
                    "title": "공식 수치",
                    "text": "정확도는 92%입니다.",
                }
            ],
        }
    )

    assert case.case_id == "case-1"
    assert case.prepared_evidence[0].source_key == "src-a"
    with pytest.raises(ValidationError):
        case.case_id = "changed"


def test_response_comparison_case_rejects_blank_dialogue_and_unknown_fields():
    with pytest.raises(ValidationError):
        ResponseComparisonCase.model_validate(
            {
                "case_id": "case-1",
                "ai_question": "   ",
                "human_response": "답",
                "allowed_source_keys": [],
                "forbidden_source_keys": [],
                "prepared_evidence": [],
            }
        )

    with pytest.raises(ValidationError):
        ResponseComparisonCase.model_validate(
            {
                "case_id": "case-1",
                "ai_question": "질문",
                "human_response": "답",
                "allowed_source_keys": [],
                "forbidden_source_keys": [],
                "prepared_evidence": [],
                "unexpected": True,
            }
        )


def test_generated_response_and_citation_and_judgment_contracts():
    response = GeneratedResponse.model_validate(
        {
            "body": "공식 자료에 따르면 92%입니다.",
            "cited_source_keys": ["src-a"],
            "cited_urls": ["https://example.com/a"],
        }
    )
    citation_check = CitationCheckResult.model_validate(
        {"passed": True, "failure_reasons": []}
    )
    judgment = PairwiseJudgment.model_validate(
        {
            "specificity_winner": "grounded",
            "naturalness_winner": "tie",
            "accuracy_winner": "grounded",
            "overall_winner": "grounded",
            "reason": "수치가 더 구체적이다.",
            "order_flipped": False,
        }
    )
    case_result = CaseComparisonResult.model_validate(
        {
            "case_id": "case-1",
            "baseline_response": response,
            "grounded_response": response,
            "baseline_citation_check": citation_check,
            "grounded_citation_check": citation_check,
            "judgment": judgment,
        }
    )
    summary = ComparisonSummary.model_validate(
        {
            "case_count": 1,
            "fatal_failure_count": 0,
            "wins": 1,
            "losses": 0,
            "ties": 0,
            "specificity_win_rate": 1.0,
            "naturalness_win_rate": 0.0,
            "accuracy_win_rate": 1.0,
            "order_flip_rate": 0.0,
            "win_rate_threshold": None,
        }
    )

    assert case_result.case_id == "case-1"
    assert summary.fatal_failure_count == 0
    with pytest.raises(ValidationError):
        PreparedEvidence.model_validate(
            {"source_key": "src-a", "url": None, "title": "t", "text": "   "}
        )
