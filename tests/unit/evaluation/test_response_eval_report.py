import pytest

from app.evaluation.contracts import (
    CaseEvalResult,
    EvalSummary,
    GeneratedResponse,
    PairwiseJudgment,
    SafetyCheckResult,
)
from app.evaluation.report import render_markdown_summary, summarize_results

pytestmark = pytest.mark.unit


def _response(body: str = "답변") -> GeneratedResponse:
    return GeneratedResponse(body=body, cited_source_keys=(), cited_urls=())


def _safety(passed: bool = True, reasons: tuple[str, ...] = ()) -> SafetyCheckResult:
    return SafetyCheckResult(passed=passed, failure_reasons=reasons)


def _judgment(
    overall: str = "grounded",
    *,
    order_flipped: bool = False,
    specificity: str = "grounded",
    naturalness: str = "tie",
    accuracy: str = "grounded",
) -> PairwiseJudgment:
    return PairwiseJudgment(
        specificity_winner=specificity,  # type: ignore[arg-type]
        naturalness_winner=naturalness,  # type: ignore[arg-type]
        accuracy_winner=accuracy,  # type: ignore[arg-type]
        overall_winner=overall,  # type: ignore[arg-type]
        reason="판정 이유",
        order_flipped=order_flipped,
    )


def test_summarize_results_counts_wins_fatals_and_rates():
    results = [
        CaseEvalResult(
            case_id="win",
            baseline_response=_response("b1"),
            grounded_response=_response("g1"),
            baseline_safety=_safety(),
            grounded_safety=_safety(),
            judgment=_judgment("grounded", specificity="grounded", naturalness="grounded", accuracy="grounded"),
        ),
        CaseEvalResult(
            case_id="loss",
            baseline_response=_response("b2"),
            grounded_response=_response("g2"),
            baseline_safety=_safety(),
            grounded_safety=_safety(),
            judgment=_judgment("baseline", specificity="baseline", naturalness="baseline", accuracy="tie"),
        ),
        CaseEvalResult(
            case_id="tie",
            baseline_response=_response("b3"),
            grounded_response=_response("g3"),
            baseline_safety=_safety(),
            grounded_safety=_safety(),
            judgment=_judgment("tie", order_flipped=True, specificity="tie", naturalness="tie", accuracy="tie"),
        ),
        CaseEvalResult(
            case_id="fatal",
            baseline_response=_response("b4"),
            grounded_response=_response("g4"),
            baseline_safety=_safety(),
            grounded_safety=_safety(False, ("unknown source cited: x",)),
            judgment=None,
        ),
    ]

    summary = summarize_results(results)

    assert summary == EvalSummary(
        case_count=4,
        fatal_failure_count=1,
        wins=1,
        losses=1,
        ties=1,
        specificity_win_rate=1 / 3,
        naturalness_win_rate=1 / 3,
        accuracy_win_rate=1 / 3,
        order_flip_rate=1 / 3,
        win_rate_threshold=None,
    )


def test_render_markdown_summary_mentions_fatal_and_undecided_threshold():
    summary = EvalSummary(
        case_count=2,
        fatal_failure_count=1,
        wins=1,
        losses=0,
        ties=0,
        specificity_win_rate=1.0,
        naturalness_win_rate=0.0,
        accuracy_win_rate=1.0,
        order_flip_rate=0.0,
        win_rate_threshold=None,
    )

    text = render_markdown_summary(summary)

    assert "치명 실수: 1" in text
    assert "승률 기준: 미정" in text
    assert "승: 1" in text
