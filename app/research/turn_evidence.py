"""대화 턴용 근거 검색."""

from __future__ import annotations

import uuid

from app.logging import get_logger
from app.research.contracts import EvidenceRequest
from app.research.indexing import (
    create_research_embeddings,
    create_research_evidence_index,
)
from app.research.prepared_evidence import format_evidence_system_text
from app.research.retrieval import retrieve_evidence

logger = get_logger(__name__)


def load_evidence_text_for_turn(
    *,
    user_id: uuid.UUID,
    manuscript_id: uuid.UUID,
    query: str,
    limit: int = 5,
) -> str:
    """인덱스에서 근거를 검색해 프롬프트용 텍스트를 만든다. 없으면 빈 문자열."""
    query = (query or "").strip()
    if not query:
        return ""
    evidence = _retrieve_for_turn(
        user_id=user_id, manuscript_id=manuscript_id, query=query, limit=limit
    )
    top_scores = [round(item.score, 3) for item in evidence.items[:3]]
    logger.info(
        "research.turn_evidence_injected",
        item_count=len(evidence.items),
        sufficient=evidence.sufficiency.sufficient,
        reason_code=evidence.sufficiency.reason_code,
        top_scores=top_scores,
    )
    return format_evidence_system_text(evidence)


def evidence_sufficient_for_turn(
    *,
    user_id: uuid.UUID,
    manuscript_id: uuid.UUID,
    query: str,
    limit: int = 5,
) -> bool:
    """이미 관련 URL이 충분히 모였는지 확인한다. 조사 플래그 낭비를 막는다."""
    query = (query or "").strip()
    if not query:
        return False
    evidence = _retrieve_for_turn(
        user_id=user_id, manuscript_id=manuscript_id, query=query, limit=limit
    )
    return evidence.sufficiency.sufficient


def _retrieve_for_turn(
    *,
    user_id: uuid.UUID,
    manuscript_id: uuid.UUID,
    query: str,
    limit: int,
):
    embeddings = create_research_embeddings()
    evidence_index = create_research_evidence_index()
    return retrieve_evidence(
        EvidenceRequest(
            user_id=user_id,
            manuscript_id=manuscript_id,
            query=query,
            limit=limit,
        ),
        evidence_index=evidence_index,
        query_embedding=embeddings.embed_query(query),
    )
