from typing import Callable

from app.evaluation.citation_allowance import check_cited_sources_are_allowed
from app.evaluation.contracts import CaseComparisonResult, ResponseComparisonCase
from app.evaluation.response_comparison import compare_response_pair
from app.evaluation.response_generation import (
    build_baseline_prompt,
    build_grounded_prompt,
    generate_response,
)

PromptInvoker = Callable[[str], str]


def compare_case_responses(
    case: ResponseComparisonCase,
    *,
    generate_invoke: PromptInvoker,
    judge_invoke: PromptInvoker,
) -> CaseComparisonResult:
    baseline = generate_response(
        prompt=build_baseline_prompt(case),
        invoke=generate_invoke,
    )
    grounded = generate_response(
        prompt=build_grounded_prompt(case),
        invoke=generate_invoke,
    )
    baseline_citation_check = check_cited_sources_are_allowed(
        response=baseline, case=case
    )
    grounded_citation_check = check_cited_sources_are_allowed(
        response=grounded, case=case
    )
    judgment = None
    if baseline_citation_check.passed and grounded_citation_check.passed:
        judgment = compare_response_pair(
            ai_question=case.ai_question,
            human_response=case.human_response,
            baseline=baseline,
            grounded=grounded,
            invoke=judge_invoke,
        )
    return CaseComparisonResult(
        case_id=case.case_id,
        baseline_response=baseline,
        grounded_response=grounded,
        baseline_citation_check=baseline_citation_check,
        grounded_citation_check=grounded_citation_check,
        judgment=judgment,
    )
