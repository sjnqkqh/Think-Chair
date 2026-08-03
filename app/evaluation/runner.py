from app.evaluation.contracts import CaseEvalResult, ResponseEvalCase
from app.evaluation.pairwise_judge import judge_pair
from app.evaluation.response_generation import (
    build_baseline_prompt,
    build_grounded_prompt,
    generate_response,
)
from app.evaluation.safety_checks import check_response_citations


def evaluate_case(
    case: ResponseEvalCase,
    *,
    generate_invoke,
    judge_invoke,
) -> CaseEvalResult:
    baseline = generate_response(
        prompt=build_baseline_prompt(case),
        invoke=generate_invoke,
    )
    grounded = generate_response(
        prompt=build_grounded_prompt(case),
        invoke=generate_invoke,
    )
    baseline_safety = check_response_citations(response=baseline, case=case)
    grounded_safety = check_response_citations(response=grounded, case=case)
    judgment = None
    if baseline_safety.passed and grounded_safety.passed:
        judgment = judge_pair(
            ai_question=case.ai_question,
            human_response=case.human_response,
            baseline=baseline,
            grounded=grounded,
            invoke=judge_invoke,
        )
    return CaseEvalResult(
        case_id=case.case_id,
        baseline_response=baseline,
        grounded_response=grounded,
        baseline_safety=baseline_safety,
        grounded_safety=grounded_safety,
        judgment=judgment,
    )
