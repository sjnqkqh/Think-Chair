import pytest

from app.evaluation.citation_allowance import check_cited_sources_are_allowed
from app.evaluation.response_comparison_contracts import (
    GeneratedResponse,
    PreparedEvidence,
    ResponseComparisonCase,
)

pytestmark = pytest.mark.unit


def _case(**overrides) -> ResponseComparisonCase:
    payload = {
        "case_id": "case-1",
        "ai_question": "수치가 맞나요?",
        "human_response": "95%라고 들었어요.",
        "allowed_source_keys": ["src-a"],
        "forbidden_source_keys": ["src-private"],
        "prepared_evidence": [
            PreparedEvidence(
                source_key="src-a",
                url="https://example.com/a",
                title="공식",
                text="정확도 92%",
            ),
            PreparedEvidence(
                source_key="src-private",
                url="https://private.example/secret",
                title="비공개",
                text="내부 수치",
            ),
        ],
    }
    payload.update(overrides)
    return ResponseComparisonCase.model_validate(payload)


def test_citation_check_passes_when_sources_are_allowed():
    result = check_cited_sources_are_allowed(
        response=GeneratedResponse(
            body=(
                "공식 자료에 따르면 92%입니다. "
                "확인: https://example.com/a"
            ),
            cited_source_keys=("src-a",),
            cited_urls=("https://example.com/a",),
        ),
        case=_case(),
    )

    assert result.passed is True
    assert result.failure_reasons == ()


def test_citation_check_fails_for_unknown_forbidden_and_ghost_urls():
    unknown = check_cited_sources_are_allowed(
        response=GeneratedResponse(
            body="다른 자료를 인용합니다.",
            cited_source_keys=("src-unknown",),
            cited_urls=(),
        ),
        case=_case(),
    )
    forbidden = check_cited_sources_are_allowed(
        response=GeneratedResponse(
            body="비공개 자료를 인용합니다.",
            cited_source_keys=("src-private",),
            cited_urls=(),
        ),
        case=_case(),
    )
    ghost_url = check_cited_sources_are_allowed(
        response=GeneratedResponse(
            body="없는 URL을 붙입니다.",
            cited_source_keys=(),
            cited_urls=("https://ghost.example/x",),
        ),
        case=_case(),
    )

    assert unknown.passed is False
    assert any("unknown" in reason for reason in unknown.failure_reasons)
    assert forbidden.passed is False
    assert any("forbidden" in reason for reason in forbidden.failure_reasons)
    assert ghost_url.passed is False
    assert any(
        "unknown" in reason or "ghost" in reason
        for reason in ghost_url.failure_reasons
    )


def test_citation_check_fails_when_cited_source_omits_matching_url():
    missing_from_list = check_cited_sources_are_allowed(
        response=GeneratedResponse(
            body="공식 자료에 따르면 92%입니다. https://example.com/a",
            cited_source_keys=("src-a",),
            cited_urls=(),
        ),
        case=_case(),
    )
    missing_from_body = check_cited_sources_are_allowed(
        response=GeneratedResponse(
            body="공식 자료에 따르면 92%입니다.",
            cited_source_keys=("src-a",),
            cited_urls=("https://example.com/a",),
        ),
        case=_case(),
    )

    assert missing_from_list.passed is False
    assert any("url" in reason for reason in missing_from_list.failure_reasons)
    assert missing_from_body.passed is False
    assert any(
        "body" in reason or "url" in reason
        for reason in missing_from_body.failure_reasons
    )


def test_citation_check_allows_empty_citations():
    result = check_cited_sources_are_allowed(
        response=GeneratedResponse(
            body="지금은 질문을 이어가겠습니다. 어떤 기준으로 95%를 들으셨나요?",
            cited_source_keys=(),
            cited_urls=(),
        ),
        case=_case(),
    )

    assert result.passed is True
    assert result.failure_reasons == ()
