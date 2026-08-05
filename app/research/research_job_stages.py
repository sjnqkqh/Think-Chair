"""조사 job 단계: 근거 수집과 종료 결과 결정.

job.status 전환은 하지 않는다. 호출부가 단계 결과를 보고 상태를 바꾼다.
"""

from __future__ import annotations

import uuid
from collections.abc import Awaitable, Callable

from pydantic import BaseModel, ConfigDict

from app.logging import get_logger
from app.models.research import ResearchJob, ResearchJobStatus
from app.research.contracts import (
    EvidenceContext,
    EvidenceRequest,
)
from app.research.retrieval import MIN_RELEVANCE_SCORE, retrieve_evidence

logger = get_logger(__name__)

EmbedQuery = Callable[[str], list[float]]
WebResearchHook = Callable[..., Awaitable[str | None]]

MAX_WEB_EXPAND_ROUNDS = 3


class EvidenceCollectionResult(BaseModel):
    """제품 경로: 조사로 모은 근거."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    evidence: EvidenceContext
    web_error: str | None = None
    # 웹 조사 예외로 세션을 rollback 했을 때. 호출부가 job 재연결·상태를 처리한다.
    session_rolled_back: bool = False


class FinalizeDecision(BaseModel):
    """호출부가 job에 적용할 종료 결과."""

    status: ResearchJobStatus
    terminal_error: str | None = None


async def collect_evidence_for_job(
    db,
    job: ResearchJob,
    *,
    query: str,
    evidence_index,
    embed_query: EmbedQuery,
    web_research: WebResearchHook | None = None,
) -> EvidenceCollectionResult:
    """인덱스 검색 → 부족하면 웹 조사 → 재검색을 최대 MAX_WEB_EXPAND_ROUNDS회 반복한다.

    충분해지거나, 웹이 관련 URL을 더 늘리지 못하면 그 전에 멈춘다. job.status는 바꾸지 않는다.
    """
    logger.info("research.evidence_collection.start", job_id=str(job.id))
    evidence = _retrieve(
        user_id=job.user_id,
        manuscript_id=job.manuscript_id,
        query=query,
        evidence_index=evidence_index,
        embed_query=embed_query,
    )
    logger.info(
        "research.evidence_collection.initial_retrieve",
        job_id=str(job.id),
        hit_count=len(evidence.items),
        sufficient=evidence.sufficiency.sufficient,
        reason_code=evidence.sufficiency.reason_code,
    )
    if evidence.sufficiency.sufficient or web_research is None:
        return EvidenceCollectionResult(evidence=evidence, web_error=None)

    web_error: str | None = None
    for round_index in range(MAX_WEB_EXPAND_ROUNDS):
        relevant_urls_before = _distinct_relevant_url_count(evidence)
        logger.info(
            "research.evidence_collection.web_expand.start",
            job_id=str(job.id),
            round=round_index + 1,
        )
        try:
            web_error = await web_research(
                db=db,
                job=job,
                query=query,
                evidence_index=evidence_index,
            )
        except Exception:
            logger.exception("research.web_research_failed", job_id=str(job.id))
            db.rollback()
            return EvidenceCollectionResult(
                evidence=evidence,
                web_error="web_research_failed",
                session_rolled_back=True,
            )

        evidence = _retrieve(
            user_id=job.user_id,
            manuscript_id=job.manuscript_id,
            query=query,
            evidence_index=evidence_index,
            embed_query=embed_query,
        )
        logger.info(
            "research.evidence_collection.reretrieve",
            job_id=str(job.id),
            round=round_index + 1,
            hit_count=len(evidence.items),
            sufficient=evidence.sufficiency.sufficient,
            reason_code=evidence.sufficiency.reason_code,
            web_error=web_error,
        )
        if evidence.sufficiency.sufficient:
            break
        if _distinct_relevant_url_count(evidence) <= relevant_urls_before:
            # 웹이 새 관련 URL을 더 모으지 못하면 라운드를 더 쓰지 않는다.
            break

    return EvidenceCollectionResult(evidence=evidence, web_error=web_error)


def decide_job_outcome(collection: EvidenceCollectionResult) -> FinalizeDecision:
    """수집된 근거만으로 호출부가 적용할 종료 결과를 정한다.

    COMPLETED: 관련 URL이 충분함. PARTIAL: 관련 청크는 있으나 URL이 부족함.
    FAILED: 관련 자료가 전혀 없음.
    """
    evidence = collection.evidence
    if evidence.sufficiency.sufficient:
        return FinalizeDecision(
            status=ResearchJobStatus.COMPLETED,
            terminal_error=None,
        )
    if evidence.sufficiency.supporting_chunk_ids:
        return FinalizeDecision(
            status=ResearchJobStatus.PARTIAL,
            terminal_error=None,
        )
    return FinalizeDecision(
        status=ResearchJobStatus.FAILED,
        terminal_error=collection.web_error or "insufficient_evidence",
    )


def _distinct_relevant_url_count(evidence: EvidenceContext) -> int:
    return len(
        {
            item.url
            for item in evidence.items
            if item.url and item.score >= MIN_RELEVANCE_SCORE
        }
    )


def _retrieve(
    *,
    user_id: uuid.UUID,
    manuscript_id: uuid.UUID,
    query: str,
    evidence_index,
    embed_query: EmbedQuery,
) -> EvidenceContext:
    return retrieve_evidence(
        EvidenceRequest(
            user_id=user_id,
            manuscript_id=manuscript_id,
            query=query,
            limit=5,
        ),
        evidence_index=evidence_index,
        query_embedding=embed_query(query),
    )
