import json

import pytest

from app.evaluation.contracts import GeneratedResponse, PreparedEvidence, ResponseComparisonCase
from app.evaluation.response_generation import (
    build_baseline_prompt,
    build_grounded_prompt,
    parse_generation_response,
)

pytestmark = pytest.mark.unit


def _case() -> ResponseComparisonCase:
    return ResponseComparisonCase(
        case_id="case-1",
        ai_question="수치가 맞나요?",
        human_response="95%라고 들었어요.",
        allowed_source_keys=("src-a",),
        forbidden_source_keys=("src-private",),
        prepared_evidence=(
            PreparedEvidence(
                source_key="src-a",
                url="https://example.com/a",
                title="공식",
                text="정확도 92%",
            ),
        ),
    )


def test_build_baseline_prompt_excludes_prepared_evidence():
    prompt = build_baseline_prompt(_case())

    assert "수치가 맞나요?" in prompt
    assert "95%라고 들었어요." in prompt
    assert "정확도 92%" not in prompt
    assert "src-a" not in prompt


def test_build_grounded_prompt_includes_prepared_evidence():
    prompt = build_grounded_prompt(_case())

    assert "수치가 맞나요?" in prompt
    assert "정확도 92%" in prompt
    assert "src-a" in prompt
    assert "https://example.com/a" in prompt
    assert "본문에 해당 페이지 주소를 그대로 넣" in prompt


def test_parse_generation_response_reads_body_and_citations():
    raw = json.dumps(
        {
            "body": "공개 자료 기준 92%입니다. https://example.com/a",
            "cited_source_keys": ["src-a"],
            "cited_urls": ["https://example.com/a"],
        },
        ensure_ascii=False,
    )

    parsed = parse_generation_response(raw)

    assert parsed == GeneratedResponse(
        body="공개 자료 기준 92%입니다. https://example.com/a",
        cited_source_keys=("src-a",),
        cited_urls=("https://example.com/a",),
    )


def test_parse_generation_response_rejects_blank_body():
    with pytest.raises(ValueError):
        parse_generation_response(
            '{"body":"   ","cited_source_keys":[],"cited_urls":[]}'
        )
