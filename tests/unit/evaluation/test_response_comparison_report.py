import pytest

from app.evaluation.response_comparison_contracts import (
    CaseComparisonResult,
    CitationCheckResult,
    ComparisonSummary,
    GeneratedResponse,
    PairwiseJudgment,
    PreparedEvidence,
)
from app.evaluation.comparison_report import (
    render_comparison_summary_markdown,
    summarize_comparison_results,
)

pytestmark = pytest.mark.unit


def _response(body: str = "답변") -> GeneratedResponse:
    return GeneratedResponse(body=body, cited_source_keys=(), cited_urls=())


def _citation_check(
    passed: bool = True, reasons: tuple[str, ...] = ()
) -> CitationCheckResult:
    return CitationCheckResult(passed=passed, failure_reasons=reasons)


def _result(
    case_id: str,
    *,
    baseline: str,
    grounded: str,
    judgment: PairwiseJudgment | None,
    grounded_citation_passed: bool = True,
    grounded_citation_reasons: tuple[str, ...] = (),
    grounded_cited_keys: tuple[str, ...] = (),
) -> CaseComparisonResult:
    evidence = (
        (
            PreparedEvidence(
                source_key="src-a",
                url="https://example.com/a",
                title="공식 가이드",
                text="타임아웃과 환경 불일치는 로그 신호가 다르다.",
            ),
        )
        if grounded_citation_passed or grounded_cited_keys
        else ()
    )
    return CaseComparisonResult(
        case_id=case_id,
        ai_question="질문이 무엇인가요?",
        human_response="사용자 답변입니다.",
        prepared_evidence=evidence,
        baseline_response=_response(baseline),
        grounded_response=GeneratedResponse(
            body=grounded,
            cited_source_keys=grounded_cited_keys,
            cited_urls=(),
        ),
        baseline_citation_check=_citation_check(),
        grounded_citation_check=_citation_check(
            grounded_citation_passed, grounded_citation_reasons
        ),
        judgment=judgment,
    )


def _judgment(
    overall: str = "grounded",
    *,
    order_flipped: bool = False,
    specificity: str = "grounded",
    naturalness: str = "tie",
    accuracy: str = "grounded",
    reason: str = "근거 참고 응답이 더 구체적이다.",
) -> PairwiseJudgment:
    from app.evaluation.response_comparison_contracts import AnswerScores

    def _pair(winner: str) -> tuple[int, int]:
        if winner == "grounded":
            return 60, 85
        if winner == "baseline":
            return 85, 60
        return 70, 70

    return PairwiseJudgment(
        baseline_scores=AnswerScores(
            specificity=_pair(specificity)[0],
            naturalness=_pair(naturalness)[0],
            accuracy=_pair(accuracy)[0],
            overall=_pair(overall)[0],
        ),
        grounded_scores=AnswerScores(
            specificity=_pair(specificity)[1],
            naturalness=_pair(naturalness)[1],
            accuracy=_pair(accuracy)[1],
            overall=_pair(overall)[1],
        ),
        specificity_winner=specificity,  # type: ignore[arg-type]
        naturalness_winner=naturalness,  # type: ignore[arg-type]
        accuracy_winner=accuracy,  # type: ignore[arg-type]
        overall_winner=overall,  # type: ignore[arg-type]
        reason=reason,
        order_flipped=order_flipped,
    )


def test_summarize_comparison_results_counts_wins_fatals_and_rates():
    results = [
        _result(
            "win",
            baseline="b1",
            grounded="g1",
            judgment=_judgment(
                "grounded",
                specificity="grounded",
                naturalness="grounded",
                accuracy="grounded",
            ),
        ),
        _result(
            "loss",
            baseline="b2",
            grounded="g2",
            judgment=_judgment(
                "baseline",
                specificity="baseline",
                naturalness="baseline",
                accuracy="tie",
            ),
        ),
        _result(
            "tie",
            baseline="b3",
            grounded="g3",
            judgment=_judgment(
                "tie",
                order_flipped=True,
                specificity="tie",
                naturalness="tie",
                accuracy="tie",
            ),
        ),
        _result(
            "fatal",
            baseline="b4",
            grounded="g4",
            judgment=None,
            grounded_citation_passed=False,
            grounded_citation_reasons=("unknown source cited: x",),
        ),
    ]

    summary = summarize_comparison_results(results)

    assert summary == ComparisonSummary(
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


def test_render_comparison_markdown_shows_both_answers_and_judgment_reason():
    summary = ComparisonSummary(
        case_count=1,
        fatal_failure_count=0,
        wins=1,
        losses=0,
        ties=0,
        specificity_win_rate=1.0,
        naturalness_win_rate=0.0,
        accuracy_win_rate=1.0,
        order_flip_rate=0.0,
        win_rate_threshold=None,
    )
    results = [
        _result(
            "ci-timeout-claim-ko",
            baseline="캐싱을 써 보셨나요?",
            grounded="타임아웃 설정 조정도 고려해 보셨나요?",
            grounded_cited_keys=("src-a",),
            judgment=_judgment(
                reason="타임아웃 설정까지 언급해 구체성이 높다."
            ),
        )
    ]

    text = render_comparison_summary_markdown(summary, results)

    assert "치명 실수: 0" in text
    assert "승률 기준: 미정" in text
    assert "### ci-timeout-claim-ko" in text
    assert "참고용으로 준비한 근거" in text
    assert "공식 가이드" in text
    assert "타임아웃과 환경 불일치는 로그 신호가 다르다." in text
    assert "응답이 인용한 출처" in text
    assert "내용: 타임아웃과 환경 불일치는 로그 신호가 다르다." in text
    assert "캐싱을 써 보셨나요?" in text
    assert "타임아웃 설정 조정도 고려해 보셨나요?" in text
    assert "근거 없는 응답" in text
    assert "근거 참고 응답" in text
    assert "타임아웃 설정까지 언급해 구체성이 높다." in text
    assert "구체성: 60 / 85 → 근거 참고 응답" in text
    assert "100점 만점" in text


def test_evidence_text_in_report_is_truncated_to_200_characters():
    long_text = "가" * 250
    summary = ComparisonSummary(
        case_count=1,
        fatal_failure_count=0,
        wins=1,
        losses=0,
        ties=0,
        specificity_win_rate=1.0,
        naturalness_win_rate=0.0,
        accuracy_win_rate=1.0,
        order_flip_rate=0.0,
        win_rate_threshold=None,
    )
    result = CaseComparisonResult(
        case_id="long-evidence",
        ai_question="질문",
        human_response="답변",
        prepared_evidence=(
            PreparedEvidence(
                source_key="src-long",
                url="https://example.com/long",
                title="긴 본문",
                text=long_text,
            ),
        ),
        baseline_response=_response("짧은 질문"),
        grounded_response=GeneratedResponse(
            body="근거 답",
            cited_source_keys=("src-long",),
            cited_urls=(),
        ),
        baseline_citation_check=_citation_check(),
        grounded_citation_check=_citation_check(),
        judgment=_judgment(),
    )

    text = render_comparison_summary_markdown(summary, [result])
    content_lines = [line for line in text.splitlines() if "내용:" in line]

    assert content_lines
    for line in content_lines:
        body = line.split("내용:", 1)[1].strip().rstrip("…")
        assert len(body) <= 200
    assert ("가" * 200) + "…" in text
    assert "가" * 250 not in text
