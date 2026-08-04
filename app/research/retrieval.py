from app.research.contracts import (
    EvidenceContext,
    EvidenceItem,
    EvidenceRequest,
    EvidenceSufficiency,
)
from app.research.evidence_index import ResearchEvidenceIndex


def retrieve_evidence(
    request: EvidenceRequest,
    *,
    evidence_index: ResearchEvidenceIndex,
    query_embedding: list[float],
) -> EvidenceContext:
    """공용·허용된 비공개 자료를 검색해 근거 컨텍스트를 만든다."""
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
    supporting_ids = [item.chunk_id for item in items]
    sufficient = bool(items)
    sufficiency = EvidenceSufficiency(
        sufficient=sufficient,
        missing_aspects=[] if sufficient else ["supporting_evidence"],
        supporting_chunk_ids=supporting_ids,
        reason_code="matched_chunks" if sufficient else "no_matching_chunks",
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
