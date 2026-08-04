import pytest
from pydantic import ValidationError

from app.evaluation.response_comparison_contracts import AnswerScores
from app.evaluation.service_growth_contracts import (
    AbsoluteJudgment,
    ServiceGrowthCase,
    ServiceGrowthCaseResult,
    ServiceGrowthRunSummary,
)

pytestmark = pytest.mark.unit


def test_service_growth_case_requires_claim_and_phase():
    case = ServiceGrowthCase.model_validate(
        {
            "case_id": "rag-improves-quality-ko",
            "phase": "say",
            "language": "ko",
            "claim": "RAG를 사용하면 LLM 응답의 품질이 좋아진다.",
            "concept": "딥다이브",
            "topic": "RAG와 응답 품질",
        }
    )
    assert case.phase == "say"
    assert "RAG" in case.claim
    with pytest.raises(ValidationError):
        case.claim = "changed"


def test_service_growth_case_rejects_blank_claim_and_bad_phase():
    with pytest.raises(ValidationError):
        ServiceGrowthCase.model_validate(
            {
                "case_id": "x",
                "phase": "say",
                    "language": "ko",
                "claim": "   ",
                "concept": "딥다이브",
                "topic": "t",
            }
        )
    with pytest.raises(ValidationError):
        ServiceGrowthCase.model_validate(
            {
                "case_id": "x",
                "phase": "outline",
                    "language": "ko",
                "claim": "주장",
                "concept": "딥다이브",
                "topic": "t",
            }
        )


def test_absolute_judgment_and_run_summary_contracts():
    judgment = AbsoluteJudgment.model_validate(
        {
            "scores": {
                "specificity": 42,
                "naturalness": 55,
                "accuracy": 40,
                "overall": 45,
            },
            "reason": "구체적 수치·한계 없이 일반론만 반복함.",
        }
    )
    assert judgment.scores.overall == 45
    summary = ServiceGrowthRunSummary.model_validate(
        {
            "case_count": 50,
            "judged_count": 48,
            "failure_count": 2,
            "avg_specificity": 41.5,
            "avg_naturalness": 50.0,
            "avg_accuracy": 38.2,
            "avg_overall": 42.0,
            "generation_model": "deepseek-chat",
            "judge_model": "deepseek-chat",
        }
    )
    assert summary.case_count == 50


def test_case_result_holds_response_and_optional_judgment():
    result = ServiceGrowthCaseResult.model_validate(
        {
            "case_id": "c1",
            "phase": "say",
            "claim": "주장",
            "topic": "주제",
            "response_body": "응답 본문",
            "evidence_text": "",
            "judgment": None,
            "error": None,
        }
    )
    assert result.judgment is None
    scores = AnswerScores(
        specificity=10, naturalness=10, accuracy=10, overall=10
    )
    judged = ServiceGrowthCaseResult.model_validate(
        {
            "case_id": "c1",
            "phase": "feedback",
            "claim": "주장",
            "topic": "주제",
            "response_body": "응답",
            "evidence_text": "근거",
            "judgment": {"scores": scores.model_dump(), "reason": "빈약함"},
            "error": None,
        }
    )
    assert judged.judgment is not None
    assert judged.judgment.scores.overall == 10
