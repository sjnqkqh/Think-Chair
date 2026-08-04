import pytest
from pydantic import ValidationError

from app.evaluation.service_growth_contracts import (
    AbsoluteAnswerScores,
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
                "reference_suggestion": 70,
                "claim_sharpening": 55,
                "knowledge_depth": 60,
                "dialogue_fit": 58,
                "next_step_clarity": 65,
                "overall": 62,
            },
            "reason": "공식 문서와 확인할 포인트를 제안함.",
        }
    )
    assert judgment.scores.reference_suggestion == 70
    summary = ServiceGrowthRunSummary.model_validate(
        {
            "case_count": 50,
            "judged_count": 48,
            "failure_count": 2,
            "avg_reference_suggestion": 41.5,
            "avg_claim_sharpening": 40.0,
            "avg_knowledge_depth": 42.0,
            "avg_dialogue_fit": 50.0,
            "avg_next_step_clarity": 38.2,
            "avg_overall": 42.0,
            "generation_model": "deepseek-chat",
            "judge_model": "deepseek-chat",
        }
    )
    assert summary.case_count == 50


def test_case_result_holds_response_and_optional_judgment():
    scores = AbsoluteAnswerScores(
        reference_suggestion=10,
        claim_sharpening=10,
        knowledge_depth=10,
        dialogue_fit=10,
        next_step_clarity=10,
        overall=10,
    )
    judged = ServiceGrowthCaseResult.model_validate(
        {
            "case_id": "c1",
            "phase": "feedback",
            "claim": "주장",
            "topic": "주제",
            "response_body": "응답",
            "evidence_text": "",
            "judgment": {"scores": scores.model_dump(), "reason": "자료 제안 없음"},
            "error": None,
        }
    )
    assert judged.judgment is not None
    assert judged.judgment.scores.overall == 10
