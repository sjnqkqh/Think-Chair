from pathlib import Path
import json

from app.evaluation.contracts import CaseEvalResult, EvalSummary, Winner


def summarize_results(results: list[CaseEvalResult]) -> EvalSummary:
    judged = [result for result in results if result.judgment is not None]
    fatal_failure_count = sum(
        1
        for result in results
        if not result.baseline_safety.passed or not result.grounded_safety.passed
    )

    wins = sum(1 for result in judged if result.judgment.overall_winner == "grounded")
    losses = sum(1 for result in judged if result.judgment.overall_winner == "baseline")
    ties = sum(1 for result in judged if result.judgment.overall_winner == "tie")
    judged_count = len(judged) or 1

    return EvalSummary(
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


def render_markdown_summary(summary: EvalSummary) -> str:
    threshold = (
        "미정"
        if summary.win_rate_threshold is None
        else f"{summary.win_rate_threshold:.0%}"
    )
    return "\n".join(
        [
            "# AI 응답 평가 요약",
            "",
            f"- 사례 수: {summary.case_count}",
            f"- 치명 실수: {summary.fatal_failure_count}",
            f"- 승: {summary.wins}",
            f"- 패: {summary.losses}",
            f"- 무승부: {summary.ties}",
            f"- 구체성 승률: {summary.specificity_win_rate:.0%}",
            f"- 자연스러움 승률: {summary.naturalness_win_rate:.0%}",
            f"- 정확성 승률: {summary.accuracy_win_rate:.0%}",
            f"- 순서 뒤집힘 비율: {summary.order_flip_rate:.0%}",
            f"- 승률 기준: {threshold}",
            "",
        ]
    )


def write_report(
    *,
    output_dir: Path,
    results: list[CaseEvalResult],
    summary: EvalSummary | None = None,
) -> tuple[Path, Path]:
    summary = summary or summarize_results(results)
    output_dir.mkdir(parents=True, exist_ok=True)
    json_path = output_dir / "results.json"
    md_path = output_dir / "summary.md"
    payload = {
        "summary": summary.model_dump(mode="json"),
        "cases": [result.model_dump(mode="json") for result in results],
    }
    json_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    md_path.write_text(render_markdown_summary(summary), encoding="utf-8")
    return json_path, md_path


def _criterion_rate(judged: list[CaseEvalResult], field_name: str) -> float:
    if not judged:
        return 0.0
    wins = 0
    for result in judged:
        winner: Winner = getattr(result.judgment, field_name)
        if winner == "grounded":
            wins += 1
    return wins / len(judged)
