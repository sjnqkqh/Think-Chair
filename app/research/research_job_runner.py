"""조사 job 실행: 검색 → (부족 시 웹 조사 훅) → baseline/grounded 비교 저장."""

from __future__ import annotations

import json
import uuid
from collections.abc import Awaitable, Callable

from app.evaluation.response_comparison import compare_response_pair
from app.evaluation.response_comparison_contracts import GeneratedResponse
from app.evaluation.response_generation import parse_generation_response
from app.logging import get_logger
from app.models.research import ResearchJob, ResearchJobStatus
from app.repositories import research_repo
from app.research.contracts import (
    EvidenceRequest,
    GroundedResponseRequest,
)
from app.research.grounded_response import generate_grounded_response
from app.research.prepared_evidence import serialize_evidence_context
from app.research.retrieval import retrieve_evidence

logger = get_logger(__name__)

EmbedQuery = Callable[[str], list[float]]
PromptInvoker = Callable[[str], str]
WebResearchHook = Callable[..., Awaitable[None]]

def _job_cancelled(db, job_id: uuid.UUID) -> bool:
    status = (
        db.query(ResearchJob.status).filter(ResearchJob.id == job_id).scalar()
    )
    return status is None or status == ResearchJobStatus.CANCELLED


async def run_research_job(
    *,
    job_id: uuid.UUID,
    db_factory,
    evidence_index,
    embed_query: EmbedQuery,
    generate_invoke: PromptInvoker,
    judge_invoke: PromptInvoker,
    generation_model: str | None = None,
    judge_model: str | None = None,
    web_research: WebResearchHook | None = None,
) -> None:
    db = db_factory()
    try:
        job = db.get(ResearchJob, job_id)
        if job is None or job.status == ResearchJobStatus.CANCELLED:
            return

        job.status = ResearchJobStatus.RUNNING
        db.commit()

        query = (job.claim_or_query or "").strip() or "관련 근거"
        evidence = retrieve_evidence(
            EvidenceRequest(
                user_id=job.user_id,
                manuscript_id=job.manuscript_id,
                query=query,
                limit=5,
            ),
            evidence_index=evidence_index,
            query_embedding=embed_query(query),
        )

        web_error: str | None = None
        if not evidence.sufficiency.sufficient and web_research is not None:
            try:
                web_error = await web_research(
                    db=db,
                    job=job,
                    query=query,
                    evidence_index=evidence_index,
                )
                evidence = retrieve_evidence(
                    EvidenceRequest(
                        user_id=job.user_id,
                        manuscript_id=job.manuscript_id,
                        query=query,
                        limit=5,
                    ),
                    evidence_index=evidence_index,
                    query_embedding=embed_query(query),
                )
            except Exception:
                web_error = "web_research_failed"
                logger.exception("research.web_research_failed", job_id=str(job_id))
                db.rollback()
                job = db.get(ResearchJob, job_id)
                if job is None or job.status == ResearchJobStatus.CANCELLED:
                    return
                job.status = ResearchJobStatus.RUNNING
                db.commit()

        baseline = _generate_baseline(
            conversation_context=query,
            invoke=generate_invoke,
        )
        grounded = generate_grounded_response(
            GroundedResponseRequest(
                phase="say",
                conversation_context=query,
                evidence=evidence,
            ),
            invoke=generate_invoke,
        )

        comparison_error = None
        judgment = None
        try:
            judgment = compare_response_pair(
                ai_question="조사로 확인할 사용자 주장/질문",
                human_response=query,
                baseline=GeneratedResponse(
                    body=baseline.body,
                    cited_source_keys=baseline.cited_source_keys,
                    cited_urls=baseline.cited_urls,
                ),
                grounded=GeneratedResponse(
                    body=grounded.text,
                    cited_source_keys=tuple(c.source_id for c in grounded.citations),
                    cited_urls=tuple(c.url for c in grounded.citations),
                ),
                invoke=judge_invoke,
            )
        except Exception as exc:
            comparison_error = type(exc).__name__
            logger.exception("research.comparison_failed", job_id=str(job_id))

        if _job_cancelled(db, job_id):
            logger.info("research.job_cancelled_before_persist", job_id=str(job_id))
            return

        job = db.get(ResearchJob, job_id)
        if job is None:
            return
        db.refresh(job)
        if job.status == ResearchJobStatus.CANCELLED:
            logger.info("research.job_cancelled_before_persist", job_id=str(job_id))
            return

        research_repo.save_response_comparison_record(
            db,
            research_job_id=job.id,
            user_id=job.user_id,
            manuscript_id=job.manuscript_id,
            message_id=job.message_id,
            baseline_body=baseline.body,
            grounded_body=grounded.text,
            baseline_cited_urls=json.dumps(
                list(baseline.cited_urls), ensure_ascii=False
            ),
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
            comparison_error=comparison_error,
            prepared_evidence_json=(
                serialize_evidence_context(evidence) if evidence.items else None
            ),
        )

        if evidence.sufficiency.sufficient and grounded.is_grounded:
            job.status = ResearchJobStatus.COMPLETED
            job.terminal_error = None
        elif evidence.items:
            job.status = ResearchJobStatus.PARTIAL
            job.terminal_error = None
        else:
            job.status = ResearchJobStatus.FAILED
            job.terminal_error = web_error or "insufficient_evidence"
        db.commit()
    except Exception:
        logger.exception("research.job_failed", job_id=str(job_id))
        try:
            db.rollback()
            job = db.get(ResearchJob, job_id)
            if job is not None and not _job_cancelled(db, job_id):
                db.refresh(job)
                if job.status != ResearchJobStatus.CANCELLED:
                    job.status = ResearchJobStatus.FAILED
                    job.terminal_error = "job_execution_error"
                    db.commit()
        except Exception:
            db.rollback()
    finally:
        db.close()


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
