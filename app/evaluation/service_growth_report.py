from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from app.evaluation.service_growth_contracts import (
    ServiceGrowthCaseResult,
    ServiceGrowthRunSummary,
)


def summarize_service_growth_results(
    results: list[ServiceGrowthCaseResult],
    *,
    generation_model: str | None = None,
    judge_model: str | None = None,
) -> ServiceGrowthRunSummary:
    judged = [result for result in results if result.judgment is not None]
    failure_count = sum(
        1 for result in results if result.error or result.judgment is None
    )

    def _avg(attr: str) -> float | None:
        if not judged:
            return None
        return sum(getattr(result.judgment.scores, attr) for result in judged) / len(
            judged
        )

    return ServiceGrowthRunSummary(
        case_count=len(results),
        judged_count=len(judged),
        failure_count=failure_count,
        avg_reference_suggestion=_avg("reference_suggestion"),
        avg_claim_sharpening=_avg("claim_sharpening"),
        avg_knowledge_depth=_avg("knowledge_depth"),
        avg_dialogue_fit=_avg("dialogue_fit"),
        avg_next_step_clarity=_avg("next_step_clarity"),
        avg_overall=_avg("overall"),
        generation_model=generation_model,
        judge_model=judge_model,
    )


def render_service_growth_markdown(
    summary: ServiceGrowthRunSummary,
    results: list[ServiceGrowthCaseResult],
    *,
    run_id: str | None = None,
) -> str:
    def _fmt(value: float | None) -> str:
        return "n/a" if value is None else f"{value:.1f}"

    lines = [
        "# 서비스 성장 관측 평가",
        "",
        "- 채점 목적: 정답 제공이 아니라, 사용자가 더 깊은 지식·명확한 근거를 쌓도록 도왔는가",
        f"- 실행 ID: {run_id or '(없음)'}",
        f"- 사례 수: {summary.case_count}",
        f"- 채점 성공: {summary.judged_count}",
        f"- 실패/미채점: {summary.failure_count}",
        f"- 평균 reference_suggestion: {_fmt(summary.avg_reference_suggestion)}",
        f"- 평균 claim_sharpening: {_fmt(summary.avg_claim_sharpening)}",
        f"- 평균 knowledge_depth: {_fmt(summary.avg_knowledge_depth)}",
        f"- 평균 dialogue_fit: {_fmt(summary.avg_dialogue_fit)}",
        f"- 평균 next_step_clarity: {_fmt(summary.avg_next_step_clarity)}",
        f"- 평균 overall: {_fmt(summary.avg_overall)}",
        f"- 생성 모델: {summary.generation_model or '(미기록)'}",
        f"- Judge 모델: {summary.judge_model or '(미기록)'}",
        "",
        "## 항목별",
        "",
    ]
    for result in results:
        lines.extend(_render_case(result))
    return "\n".join(lines)


def write_service_growth_report(
    *,
    output_dir: Path,
    results: list[ServiceGrowthCaseResult],
    summary: ServiceGrowthRunSummary | None = None,
    generation_model: str | None = None,
    judge_model: str | None = None,
    run_id: str | None = None,
) -> tuple[Path, Path]:
    summary = summary or summarize_service_growth_results(
        results,
        generation_model=generation_model,
        judge_model=judge_model,
    )
    run_id = run_id or datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    output_dir.mkdir(parents=True, exist_ok=True)
    json_path = output_dir / f"{run_id}.json"
    markdown_path = output_dir / f"{run_id}.md"
    payload = {
        "summary": summary.model_dump(mode="json"),
        "cases": [result.model_dump(mode="json") for result in results],
    }
    json_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    markdown_path.write_text(
        render_service_growth_markdown(summary, results, run_id=run_id),
        encoding="utf-8",
    )
    return json_path, markdown_path


def _render_case(result: ServiceGrowthCaseResult) -> list[str]:
    lines = [
        f"### {result.case_id}",
        "",
        f"- phase: `{result.phase}`",
        f"- topic: {result.topic}",
        f"- claim: {result.claim}",
        f"- evidence_injected: {'yes' if result.evidence_text.strip() else 'no'}",
    ]
    if result.error:
        lines.extend([f"- error: {result.error}", ""])
        return lines
    lines.extend(["", "**응답**", "", result.response_body or "(빈 응답)", ""])
    if result.judgment is None:
        lines.extend(["**판정**: 없음", ""])
        return lines
    scores = result.judgment.scores
    lines.extend(
        [
            "**판정** (지식 심화·근거 제안, 0~100)",
            f"- overall: {scores.overall}",
            f"- reference_suggestion: {scores.reference_suggestion}",
            f"- claim_sharpening: {scores.claim_sharpening}",
            f"- knowledge_depth: {scores.knowledge_depth}",
            f"- dialogue_fit: {scores.dialogue_fit}",
            f"- next_step_clarity: {scores.next_step_clarity}",
            f"- reason: {result.judgment.reason}",
            "",
        ]
    )
    return lines
