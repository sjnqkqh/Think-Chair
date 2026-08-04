from pathlib import Path

import pytest

from app.evaluation.service_growth_contracts import (
    AbsoluteAnswerScores,
    AbsoluteJudgment,
    ServiceGrowthCaseResult,
)
from app.evaluation.service_growth_report import (
    render_service_growth_markdown,
    summarize_service_growth_results,
    write_service_growth_report,
)

pytestmark = pytest.mark.unit


def _result(**overrides):
    base = {
        "case_id": "c1",
        "phase": "say",
        "claim": "주장",
        "topic": "주제",
        "response_body": "응답 본문",
        "evidence_text": "",
        "judgment": AbsoluteJudgment(
            scores=AbsoluteAnswerScores(
                reference_suggestion=20,
                claim_sharpening=35,
                knowledge_depth=30,
                dialogue_fit=50,
                next_step_clarity=25,
                overall=28,
            ),
            reason="참고자료 제안 없이 동의만 함",
        ),
        "error": None,
    }
    base.update(overrides)
    return ServiceGrowthCaseResult.model_validate(base)


def test_summarize_and_render_markdown_includes_totals_and_items():
    results = [
        _result(case_id="c1"),
        _result(
            case_id="c2",
            judgment=None,
            error="boom",
            response_body="",
        ),
    ]
    summary = summarize_service_growth_results(
        results,
        generation_model="deepseek-chat",
        judge_model="deepseek-chat",
    )
    assert summary.case_count == 2
    assert summary.judged_count == 1
    assert summary.avg_overall == 28.0
    assert summary.avg_reference_suggestion == 20.0

    md = render_service_growth_markdown(summary, results, run_id="test-run")
    assert "명확한 근거" in md or "깊은 지식" in md
    assert "reference_suggestion" in md
    assert "### c1" in md
    assert "참고자료 제안 없이" in md


def test_write_service_growth_report_creates_md_and_json(tmp_path: Path):
    results = [_result()]
    json_path, md_path = write_service_growth_report(
        output_dir=tmp_path,
        results=results,
        run_id="20260804-120000",
        generation_model="m1",
        judge_model="m2",
    )
    assert json_path.exists()
    assert md_path.exists()
    assert "reference_suggestion" in md_path.read_text(encoding="utf-8")
