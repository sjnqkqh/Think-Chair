"""조사 job 실행 호출부: 제품 완료 후 평가는 best-effort로만 남긴다."""

from __future__ import annotations

import uuid
from collections.abc import Awaitable, Callable

from app.logging import get_logger
from app.research.research_job_context import ResearchJobContext
from app.research.research_job_stages import (
    collect_evidence_for_job,
    decide_job_outcome,
    evaluate_research_responses,
    save_research_comparison_record,
)

logger = get_logger(__name__)

EmbedQuery = Callable[[str], list[float]]
PromptInvoker = Callable[[str], str]
WebResearchHook = Callable[..., Awaitable[str | None]]


async def run_research_job(
    *,
    job_id: uuid.UUID,
    db_factory,
    evidence_index,
    embed_query: EmbedQuery,
    generate_invoke: PromptInvoker | None = None,
    judge_invoke: PromptInvoker | None = None,
    generation_model: str | None = None,
    judge_model: str | None = None,
    web_research: WebResearchHook | None = None,
) -> None:
    job_session = ResearchJobContext(db_factory(), job_id)
    try:
        if not job_session.begin():
            return

        collection = await collect_evidence_for_job(
            job_session.db,
            job_session.job,
            query=job_session.query,
            evidence_index=evidence_index,
            embed_query=embed_query,
            web_research=web_research,
        )
        if collection.session_rolled_back:
            if not job_session.recover_after_rollback():
                return

        if job_session.cancelled():
            return

        decision = decide_job_outcome(collection)

        if not job_session.reload_if_active():
            return

        job_session.finish(
            status=decision.status,
            terminal_error=decision.terminal_error,
        )

        if generate_invoke is None or judge_invoke is None:
            return
        if job_session.cancelled():
            return
        logger.info(
            "research.evaluation.begin",
            job_id=str(job_id),
            reason=(
                "웹 수집·인덱싱(제품)과 별도로 DeepSeek baseline/grounded/"
                "pairwise 관측 평가를 실행한다"
            ),
        )
        try:
            evaluation = evaluate_research_responses(
                query=job_session.query,
                evidence=collection.evidence,
                generate_invoke=generate_invoke,
                judge_invoke=judge_invoke,
            )
            if job_session.cancelled():
                return
            save_research_comparison_record(
                job_session.db,
                job_session.job,
                evaluation=evaluation,
                generation_model=generation_model,
                judge_model=judge_model,
            )
            job_session.db.commit()
        except Exception:
            logger.exception(
                "research.evaluation_failed_after_product_finish",
                job_id=str(job_id),
            )
            job_session.db.rollback()
    except Exception:
        logger.exception("research.job_failed", job_id=str(job_id))
        job_session.fail_execution()
    finally:
        job_session.close()
