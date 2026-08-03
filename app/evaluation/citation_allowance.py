from app.evaluation.contracts import (
    CitationCheckResult,
    GeneratedResponse,
    ResponseComparisonCase,
)


def check_cited_sources_are_allowed(
    *,
    response: GeneratedResponse,
    case: ResponseComparisonCase,
) -> CitationCheckResult:
    """출처 존재·허용·본문 URL 포함 여부만 검사한다. 내용 일치는 검사하지 않는다."""
    allowed = set(case.allowed_source_keys)
    forbidden = set(case.forbidden_source_keys)
    evidence_by_key = {
        evidence.source_key: evidence for evidence in case.prepared_evidence
    }
    allowed_urls = {
        evidence.url
        for evidence in case.prepared_evidence
        if evidence.source_key in allowed and evidence.url
    }
    cited_urls = set(response.cited_urls)
    reasons: list[str] = []

    for source_key in response.cited_source_keys:
        if source_key in forbidden:
            reasons.append(f"forbidden source cited: {source_key}")
            continue
        if source_key not in allowed:
            reasons.append(f"unknown source cited: {source_key}")
            continue

        evidence = evidence_by_key.get(source_key)
        if evidence is None or not evidence.url:
            reasons.append(f"cited source has no url to share: {source_key}")
            continue
        if evidence.url not in cited_urls:
            reasons.append(f"cited source missing matching url: {source_key}")
            continue
        if evidence.url not in response.body:
            reasons.append(f"cited url missing from body: {evidence.url}")

    for url in response.cited_urls:
        if url not in allowed_urls:
            reasons.append(f"unknown or ghost url cited: {url}")

    return CitationCheckResult(passed=not reasons, failure_reasons=tuple(reasons))
