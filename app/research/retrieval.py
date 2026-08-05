from app.logging import get_logger
from app.research.contracts import (
    EvidenceContext,
    EvidenceItem,
    EvidenceRequest,
    EvidenceSufficiency,
)
from app.research.evidence_index import ResearchEvidenceIndex

MIN_RELEVANCE_SCORE = 0.45
MIN_DISTINCT_RELEVANT_URLS = 3
logger = get_logger(__name__)


def retrieve_evidence(
    request: EvidenceRequest,
    *,
    evidence_index: ResearchEvidenceIndex,
    query_embedding: list[float],
) -> EvidenceContext:
    """공용·허용된 비공개 자료를 검색해 근거 컨텍스트를 만든다.

    무관한 청크가 섞여도 충분성 판단에 영향을 주지 않도록, 점수가 낮은 청크는
    관련 자료에서 제외하고 서로 다른 출처 URL 개수로 충분성을 정한다.
    """
    public_hits = evidence_index.query_chunks(
        scope="public",
        query_embedding=query_embedding,
        limit=request.limit,
    )
    private_hits = evidence_index.query_chunks(
        scope="private",
        query_embedding=query_embedding,
        limit=request.limit,
        where={
            "$and": [
                {"owner_user_id": str(request.user_id)},
                {"owner_manuscript_id": str(request.manuscript_id)},
            ]
        },
    )
    ranked = sorted(
        (*public_hits, *private_hits),
        key=lambda hit: (
            float("inf") if hit["distance"] is None else float(hit["distance"])
        ),
    )[: request.limit]

    items = [_to_evidence_item(hit) for hit in ranked]
    relevant_items = [item for item in items if item.score >= MIN_RELEVANCE_SCORE]
    distinct_relevant_urls = {item.url for item in relevant_items if item.url}
    sufficient = len(distinct_relevant_urls) >= MIN_DISTINCT_RELEVANT_URLS

    if sufficient:
        reason_code = "matched_chunks"
    elif relevant_items:
        reason_code = "insufficient_distinct_urls"
    else:
        reason_code = "no_matching_chunks"

    sufficiency = EvidenceSufficiency(
        sufficient=sufficient,
        missing_aspects=[] if sufficient else ["supporting_evidence"],
        supporting_chunk_ids=[item.chunk_id for item in relevant_items],
        reason_code=reason_code,
    )
    logger.info(
        "research.evidence_retrieved",
        hit_count=len(items),
        sufficient=sufficient,
        reason_code=sufficiency.reason_code,
    )
    return EvidenceContext(
        items=items,
        sufficiency=sufficiency,
        is_grounded=sufficient,
        warning_code=None if sufficient else "insufficient_evidence",
    )


def _to_evidence_item(hit: dict) -> EvidenceItem:
    metadata = hit.get("metadata") or {}
    distance = hit.get("distance")
    score = 0.0 if distance is None else 1.0 / (1.0 + float(distance))
    url = str(metadata.get("canonical_url") or metadata.get("source_url") or "")
    return EvidenceItem(
        chunk_id=str(metadata.get("chunk_id") or hit.get("id") or ""),
        source_id=str(metadata.get("source_id") or ""),
        excerpt=str(hit.get("document") or ""),
        score=score,
        title=str(metadata.get("title") or ""),
        url=url,
        language=str(metadata.get("language") or "und"),
        published_at=metadata.get("published_at"),
        fetched_at=metadata.get("fetched_at"),
        source_type=metadata.get("source_type"),
        claim_relevance=metadata.get("claim_relevance"),
        freshness=metadata.get("freshness"),
        is_primary_source=metadata.get("is_primary_source"),
        independence_group=metadata.get("independence_group"),
        expected_treatment=metadata.get("expected_treatment"),
    )
