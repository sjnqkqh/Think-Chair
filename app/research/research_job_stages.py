"""조사 job 단계: 제품(근거 수집) / 평가(응답·비교) / 기록 저장.

job.status 전환은 하지 않는다. 호출부가 단계 결과를 보고 상태를 바꾼다.
"""

from __future__ import annotations

import uuid
from collections.abc import Awaitable, Callable

from pydantic import BaseModel, ConfigDict

from app.evaluation.response_comparison import compare_response_pair
from app.evaluation.response_comparison_contracts import (
    GeneratedResponse,
    PairwiseJudgment,
)
from app.evaluation.response_generation import parse_generation_response
from app.logging import get_logger
from app.models.research import ResearchJob, ResearchJobStatus, ResponseComparisonRecord
from app.repositories import research_repo
from app.research.contracts import (
    EvidenceContext,
    EvidenceRequest,
    GroundedResponseRequest,
    GroundedResponseResult,
)
from app.research.grounded_response import generate_grounded_response
from app.research.retrieval import MIN_RELEVANCE_SCORE, retrieve_evidence

logger = get_logger(__name__)

EmbedQuery = Callable[[str], list[float]]
PromptInvoker = Callable[[str], str]
WebResearchHook = Callable[..., Awaitable[str | None]]

MAX_WEB_EXPAND_ROUNDS = 3


class EvidenceCollectionResult(BaseModel):
    """제품 경로: 조사로 모은 근거."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    evidence: EvidenceContext
    web_error: str | None = None
    # 웹 조사 예외로 세션을 rollback 했을 때. 호출부가 job 재연결·상태를 처리한다.
    session_rolled_back: bool = False


class ResponsePairResult(BaseModel):
    """평가용 baseline / grounded 쌍."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    baseline: GeneratedResponse
    grounded: GroundedResponseResult


class EvaluationResult(BaseModel):
    """평가 경로: 응답 쌍 + (선택) pairwise 판정."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    responses: ResponsePairResult
    judgment: PairwiseJudgment | None = None
    comparison_error: str | None = None


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


def evaluate_research_responses(
    *,
    query: str,
    evidence: EvidenceContext,
    generate_invoke: PromptInvoker,
    judge_invoke: PromptInvoker,
) -> EvaluationResult:
    """baseline/grounded 생성과 LLM 비교. 비교 실패는 결과 필드로만 남긴다."""
    responses = ResponsePairResult(
        baseline=_generate_baseline(conversation_context=query, invoke=generate_invoke),
        grounded=generate_grounded_response(
            GroundedResponseRequest(
                phase="say",
                conversation_context=query,
                evidence=evidence,
            ),
            invoke=generate_invoke,
        ),
    )
    judgment = None
    comparison_error = None
    try:
        judgment = compare_response_pair(
            ai_question="조사로 확인할 사용자 주장/질문",
            human_response=query,
            baseline=GeneratedResponse(
                body=responses.baseline.body,
                cited_source_keys=responses.baseline.cited_source_keys,
                cited_urls=responses.baseline.cited_urls,
            ),
            grounded=GeneratedResponse(
                body=responses.grounded.text,
                cited_source_keys=tuple(
                    c.source_id for c in responses.grounded.citations
                ),
                cited_urls=tuple(c.url for c in responses.grounded.citations),
            ),
            invoke=judge_invoke,
        )
    except Exception as exc:
        comparison_error = type(exc).__name__
        logger.exception("research.comparison_failed")
    return EvaluationResult(
        responses=responses,
        judgment=judgment,
        comparison_error=comparison_error,
    )


def save_research_comparison_record(
    db,
    job: ResearchJob,
    *,
    evaluation: EvaluationResult,
    generation_model: str | None,
    judge_model: str | None,
) -> None:
    """평가 비교 기록만 저장한다. job.status는 바꾸지 않는다."""
    record = ResponseComparisonRecord.from_job_evaluation(
        job,
        baseline=evaluation.responses.baseline,
        grounded=evaluation.responses.grounded,
        judgment=evaluation.judgment,
        generation_model=generation_model,
        judge_model=judge_model,
        comparison_error=evaluation.comparison_error,
    )
    research_repo.save_response_comparison_record(db, record)


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


def _generate_baseline(
    *,
    conversation_context: str,
    invoke: PromptInvoker,
) -> GeneratedResponse:
    prompt = f"""당신은 사용자의 글쓰기 대화를 이어가는 AI입니다.
외부 검색 자료는 없습니다. 근거가 부족하면 단정하지 말고 확인 질문으로 이어가도 됩니다.

[대화 맥락]
{conversation_context}

출력은 JSON 객체 하나만 출력하십시오.
{{"body":"다음 AI 응답","cited_source_keys":[],"cited_urls":[]}}"""
    return parse_generation_response(invoke(prompt))
