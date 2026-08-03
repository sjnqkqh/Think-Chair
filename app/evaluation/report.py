import json
from pathlib import Path

from app.evaluation.contracts import (
    CaseComparisonResult,
    ComparisonSummary,
    ComparisonWinner,
)

_WINNER_LABELS = {
    "baseline": "근거 없는 응답",
    "grounded": "근거 참고 응답",
    "tie": "무승부",
}


def summarize_comparison_results(
    results: list[CaseComparisonResult],
) -> ComparisonSummary:
    judged = [result for result in results if result.judgment is not None]
    fatal_failure_count = sum(
        1
        for result in results
        if not result.baseline_citation_check.passed
        or not result.grounded_citation_check.passed
    )

    wins = sum(1 for result in judged if result.judgment.overall_winner == "grounded")
    losses = sum(1 for result in judged if result.judgment.overall_winner == "baseline")
    ties = sum(1 for result in judged if result.judgment.overall_winner == "tie")
    judged_count = len(judged) or 1

    return ComparisonSummary(
        case_count=len(results),
        fatal_failure_count=fatal_failure_count,
        wins=wins,
        losses=losses,
        ties=ties,
        specificity_win_rate=_criterion_rate(judged, "specificity_winner"),
        naturalness_win_rate=_criterion_rate(judged, "naturalness_winner"),
        accuracy_win_rate=_criterion_rate(judged, "accuracy_winner"),
        order_flip_rate=sum(1 for result in judged if result.judgment.order_flipped)
        / judged_count,
        win_rate_threshold=None,
    )


def render_comparison_summary_markdown(
    summary: ComparisonSummary,
    results: list[CaseComparisonResult] | None = None,
) -> str:
    threshold = (
        "미정"
        if summary.win_rate_threshold is None
        else f"{summary.win_rate_threshold:.0%}"
    )
    lines = [
        "# AI 응답 비교 평가 요약",
        "",
        f"- 사례 수: {summary.case_count}",
        f"- 치명 실수: {summary.fatal_failure_count}",
        f"- 승(근거 참고): {summary.wins}",
        f"- 패(근거 없는 쪽이 우세): {summary.losses}",
        f"- 무승부: {summary.ties}",
        f"- 구체성 승률: {summary.specificity_win_rate:.0%}",
        f"- 자연스러움 승률: {summary.naturalness_win_rate:.0%}",
        f"- 정확성 승률: {summary.accuracy_win_rate:.0%}",
        f"- 순서 뒤집힘 비율: {summary.order_flip_rate:.0%}",
        f"- 승률 기준: {threshold}",
        "",
    ]
    if results:
        lines.extend(["## 사례별 비교", ""])
        for result in results:
            lines.extend(_render_case_section(result))
    return "\n".join(lines)


def write_comparison_report(
    *,
    output_dir: Path,
    results: list[CaseComparisonResult],
    summary: ComparisonSummary | None = None,
) -> tuple[Path, Path]:
    summary = summary or summarize_comparison_results(results)
    output_dir.mkdir(parents=True, exist_ok=True)
    json_path = output_dir / "results.json"
    markdown_path = output_dir / "summary.md"
    payload = {
        "summary": summary.model_dump(mode="json"),
        "cases": [result.model_dump(mode="json") for result in results],
    }
    json_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    markdown_path.write_text(
        render_comparison_summary_markdown(summary, results),
        encoding="utf-8",
    )
    return json_path, markdown_path


def _render_case_section(result: CaseComparisonResult) -> list[str]:
    evidence = (
        ", ".join(result.prepared_evidence_keys)
        if result.prepared_evidence_keys
        else "(없음)"
    )
    lines = [
        f"### {result.case_id}",
        "",
        "**대화**",
        f"- AI 질문: {result.ai_question}",
        f"- 사용자 답변: {result.human_response}",
        f"- 준비된 근거: {evidence}",
        "",
        "**근거 없는 응답**",
        result.baseline_response.body,
        _format_citations(result.baseline_response.cited_source_keys),
        _format_citation_check("근거 없는 응답", result.baseline_citation_check.passed, result.baseline_citation_check.failure_reasons),
        "",
        "**근거 참고 응답**",
        result.grounded_response.body,
        _format_citations(result.grounded_response.cited_source_keys),
        _format_citation_check("근거 참고 응답", result.grounded_citation_check.passed, result.grounded_citation_check.failure_reasons),
        "",
    ]
    if result.judgment is None:
        lines.extend(["**판정**: 출처 규칙 실패로 비교 판정 생략", ""])
        return lines

    judgment = result.judgment
    lines.extend(
        [
            "**판정**",
            f"- 전체: {_winner_label(judgment.overall_winner)}"
            + (" (순서 바꿔 평가 시 뒤집힘 → 무승부 처리)" if judgment.order_flipped else ""),
            f"- 구체성: {_winner_label(judgment.specificity_winner)}",
            f"- 자연스러움: {_winner_label(judgment.naturalness_winner)}",
            f"- 정확성: {_winner_label(judgment.accuracy_winner)}",
            f"- 이유: {judgment.reason}",
            "",
        ]
    )
    return lines


def _winner_label(winner: ComparisonWinner) -> str:
    return _WINNER_LABELS[winner]


def _format_citations(cited_source_keys: tuple[str, ...]) -> str:
    if not cited_source_keys:
        return "- 인용 출처: (없음)"
    return f"- 인용 출처: {', '.join(cited_source_keys)}"


def _format_citation_check(
    label: str, passed: bool, reasons: tuple[str, ...]
) -> str:
    if passed:
        return f"- 출처 규칙: {label} 통과"
    joined = "; ".join(reasons) if reasons else "실패"
    return f"- 출처 규칙: {label} 실패 ({joined})"


def _criterion_rate(judged: list[CaseComparisonResult], field_name: str) -> float:
    if not judged:
        return 0.0
    wins = 0
    for result in judged:
        winner: ComparisonWinner = getattr(result.judgment, field_name)
        if winner == "grounded":
            wins += 1
    return wins / len(judged)
