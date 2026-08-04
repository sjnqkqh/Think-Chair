"""조사 job 단계: 제품(근거 수집) / 평가(응답·비교) / 기록 저장.

job.status 전환은 하지 않는다. 호출부가 단계 결과를 보고 상태를 바꾼다.
"""

from __future__ import annotations

import json
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
from app.models.research import ResearchJob, ResearchJobStatus
from app.repositories import research_repo
from app.research.contracts import (
    EvidenceContext,
    EvidenceRequest,
    GroundedResponseRequest,
    GroundedResponseResult,
)
from app.research.grounded_response import generate_grounded_response
from app.research.prepared_evidence import serialize_evidence_context
from app.research.retrieval import retrieve_evidence

logger = get_logger(__name__)

EmbedQuery = Callable[[str], list[float]]
PromptInvoker = Callable[[str], str]
WebResearchHook = Callable[..., Awaitable[str | None]]


class EvidenceCollectionResult(BaseModel):
    """제품 경로: 조사로 모은 근거."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    evidence: EvidenceContext
    web_error: str | None = None
    session_rolled_back: bool = False  # 웹 조사 예외로 세션을 rollback 했을 때. 호출부가 job 재연결·상태를 처리한다.

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
    prepared_evidence_json: str | None = None


async def collect_evidence_for_job(
    db,
    job: ResearchJob,
    *,
    query: str,
    evidence_index,
    embed_query: EmbedQuery,
    web_research: WebResearchHook | None = None,
) -> EvidenceCollectionResult:
    """인덱스 검색 → 부족하면 웹 조사 → 재검색. job.status는 바꾸지 않는다."""
    evidence = _retrieve(
        user_id=job.user_id,
        manuscript_id=job.manuscript_id,
        query=query,
        evidence_index=evidence_index,
        embed_query=embed_query,
    )
    if evidence.sufficiency.sufficient or web_research is None:
        return EvidenceCollectionResult(evidence=evidence, web_error=None)

    try:
        web_error = await web_research(
            db=db,
            job=job,
            query=query,
            evidence_index=evidence_index,
        )
        evidence = _retrieve(
            user_id=job.user_id,
            manuscript_id=job.manuscript_id,
            query=query,
            evidence_index=evidence_index,
            embed_query=embed_query,
        )
        return EvidenceCollectionResult(evidence=evidence, web_error=web_error)
    except Exception:
        logger.exception("research.web_research_failed", job_id=str(job.id))
        db.rollback()
        return EvidenceCollectionResult(
            evidence=evidence,
            web_error="web_research_failed",
            session_rolled_back=True,
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


def decide_job_outcome(
    collection: EvidenceCollectionResult,
    evaluation: EvaluationResult,
) -> FinalizeDecision:
    """제품 근거·grounded 품질로 호출부가 적용할 종료 결과를 정한다."""
    evidence = collection.evidence
    grounded = evaluation.responses.grounded
    prepared = serialize_evidence_context(evidence) if evidence.items else None
    if evidence.sufficiency.sufficient and grounded.is_grounded:
        return FinalizeDecision(
            status=ResearchJobStatus.COMPLETED,
            terminal_error=None,
            prepared_evidence_json=prepared,
        )
    if evidence.items:
        return FinalizeDecision(
            status=ResearchJobStatus.PARTIAL,
            terminal_error=None,
            prepared_evidence_json=prepared,
        )
    return FinalizeDecision(
        status=ResearchJobStatus.FAILED,
        terminal_error=collection.web_error or "insufficient_evidence",
        prepared_evidence_json=prepared,
    )


def save_research_comparison_record(
    db,
    job: ResearchJob,
    *,
    collection: EvidenceCollectionResult,
    evaluation: EvaluationResult,
    decision: FinalizeDecision,
    generation_model: str | None,
    judge_model: str | None,
) -> None:
    """비교·prepared evidence 행만 저장한다. job.status는 바꾸지 않는다."""
    baseline = evaluation.responses.baseline
    grounded = evaluation.responses.grounded
    judgment = evaluation.judgment
    research_repo.save_response_comparison_record(
        db,
        research_job_id=job.id,
        user_id=job.user_id,
        manuscript_id=job.manuscript_id,
        message_id=job.message_id,
        baseline_body=baseline.body,
        grounded_body=grounded.text,
        baseline_cited_urls=json.dumps(list(baseline.cited_urls), ensure_ascii=False),
        grounded_cited_urls=json.dumps(
            [c.url for c in grounded.citations], ensure_ascii=False
        ),
        baseline_citation_passed=True,
        grounded_citation_passed=grounded.is_grounded,
        citation_failure_reasons=grounded.warning_code,
        specificity_winner=judgment.specificity_winner if judgment else None,
        naturalness_winner=judgment.naturalness_winner if judgment else None,
        accuracy_winner=judgment.accuracy_winner if judgment else None,
        overall_winner=judgment.overall_winner if judgment else None,
        judgment_reason=judgment.reason if judgment else None,
        order_flipped=judgment.order_flipped if judgment else None,
        generation_model=generation_model,
        judge_model=judge_model,
        comparison_error=evaluation.comparison_error,
        prepared_evidence_json=decision.prepared_evidence_json,
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
