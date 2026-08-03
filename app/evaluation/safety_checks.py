from app.evaluation.contracts import (
    GeneratedResponse,
    ResponseEvalCase,
    SafetyCheckResult,
)


def check_response_citations(
    *,
    response: GeneratedResponse,
    case: ResponseEvalCase,
) -> SafetyCheckResult:
    """출처 존재·허용 여부만 검사한다. 내용 일치는 검사하지 않는다."""
    allowed = set(case.allowed_source_keys)
    forbidden = set(case.forbidden_source_keys)
    allowed_urls = {
        evidence.url
        for evidence in case.prepared_evidence
        if evidence.source_key in allowed and evidence.url
    }
    reasons: list[str] = []

    for source_key in response.cited_source_keys:
        if source_key in forbidden:
            reasons.append(f"forbidden source cited: {source_key}")
        elif source_key not in allowed:
            reasons.append(f"unknown source cited: {source_key}")

    for url in response.cited_urls:
        if url not in allowed_urls:
            reasons.append(f"unknown or ghost url cited: {url}")

    return SafetyCheckResult(passed=not reasons, failure_reasons=tuple(reasons))
