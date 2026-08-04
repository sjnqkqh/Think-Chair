import json
from pathlib import Path

from app.evaluation.response_comparison_contracts import (
    CaseComparisonResult,
    ComparisonSummary,
    ComparisonWinner,
    PreparedEvidence,
)

_WINNER_LABELS = {
    "baseline": "근거 없는 응답",
    "grounded": "근거 참고 응답",
    "tie": "무승부",
}
_EVIDENCE_TEXT_PREVIEW_LIMIT = 200


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
    lines = [
        f"### {result.case_id}",
        "",
        "**대화**",
        f"- AI 질문: {result.ai_question}",
        f"- 사용자 답변: {result.human_response}",
        "",
        "**참고용으로 준비한 근거**",
        *_format_prepared_evidence(result.prepared_evidence),
        "",
        "**근거 없는 응답**",
        result.baseline_response.body,
        *_format_cited_evidence(
            result.baseline_response.cited_source_keys,
            result.prepared_evidence,
        ),
        _format_citation_check(
            "근거 없는 응답",
            result.baseline_citation_check.passed,
            result.baseline_citation_check.failure_reasons,
        ),
        "",
        "**근거 참고 응답**",
        result.grounded_response.body,
        *_format_cited_evidence(
            result.grounded_response.cited_source_keys,
            result.prepared_evidence,
        ),
        _format_citation_check(
            "근거 참고 응답",
            result.grounded_citation_check.passed,
            result.grounded_citation_check.failure_reasons,
        ),
        "",
    ]
    if result.judgment is None:
        lines.extend(["**판정**: 출처 규칙 실패로 비교 판정 생략", ""])
        return lines

    judgment = result.judgment
    baseline = judgment.baseline_scores
    grounded = judgment.grounded_scores
    lines.extend(
        [
            "**판정** (100점 만점)",
            f"- 전체: baseline {baseline.overall} / grounded {grounded.overall}"
            f" → {_winner_label(judgment.overall_winner)}"
            + (
                " (순서 바꿔 평가 시 뒤집힘 → 무승부 처리)"
                if judgment.order_flipped
                else ""
            ),
            f"- 구체성: {baseline.specificity} / {grounded.specificity}"
            f" → {_winner_label(judgment.specificity_winner)}",
            f"- 자연스러움: {baseline.naturalness} / {grounded.naturalness}"
            f" → {_winner_label(judgment.naturalness_winner)}",
            f"- 정확성: {baseline.accuracy} / {grounded.accuracy}"
            f" → {_winner_label(judgment.accuracy_winner)}",
            f"- 이유: {judgment.reason}",
            "",
        ]
    )
    return lines


def _winner_label(winner: ComparisonWinner) -> str:
    return _WINNER_LABELS[winner]


def _format_prepared_evidence(
    evidence_items: tuple[PreparedEvidence, ...],
) -> list[str]:
    if not evidence_items:
        return ["- (없음)"]
    lines: list[str] = []
    for item in evidence_items:
        url = item.url or "(URL 없음)"
        lines.extend(
            [
                f"- `{item.source_key}` | {item.title}",
                f"  - URL: {url}",
                f"  - 내용: {_preview_evidence_text(item.text)}",
            ]
        )
    return lines


def _format_cited_evidence(
    cited_source_keys: tuple[str, ...],
    prepared_evidence: tuple[PreparedEvidence, ...],
) -> list[str]:
    if not cited_source_keys:
        return ["- 응답이 인용한 출처: (없음)"]

    by_key = {item.source_key: item for item in prepared_evidence}
    lines = ["- 응답이 인용한 출처:"]
    for key in cited_source_keys:
        item = by_key.get(key)
        if item is None:
            lines.append(f"  - `{key}` (준비 목록에 없음 — 본문 확인 불가)")
            continue
        url = item.url or "(URL 없음)"
        lines.extend(
            [
                f"  - `{item.source_key}` | {item.title}",
                f"    - URL: {url}",
                f"    - 내용: {_preview_evidence_text(item.text)}",
            ]
        )
    return lines


def _preview_evidence_text(text: str) -> str:
    compact = " ".join(text.split())
    if len(compact) <= _EVIDENCE_TEXT_PREVIEW_LIMIT:
        return compact
    return compact[:_EVIDENCE_TEXT_PREVIEW_LIMIT] + "…"


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
