from pathlib import Path

import pytest

from app.evaluation.response_comparison_contracts import AnswerScores
from app.evaluation.service_growth_contracts import (
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
            scores=AnswerScores(
                specificity=40, naturalness=50, accuracy=35, overall=42
            ),
            reason="일반론만 있음",
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
    assert summary.failure_count == 1
    assert summary.avg_overall == 42.0

    md = render_service_growth_markdown(summary, results, run_id="test-run")
    assert "# 서비스 성장 관측 평가" in md
    assert "평균 overall: 42.0" in md
    assert "### c1" in md
    assert "### c2" in md
    assert "일반론만 있음" in md


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
    assert "평균 overall" in md_path.read_text(encoding="utf-8")
