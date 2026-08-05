"""조사 job 실행 호출부: 근거 수집 후 제품 상태만 확정한다."""

from __future__ import annotations

import uuid
from collections.abc import Awaitable, Callable

from app.logging import get_logger
from app.research.research_job_context import ResearchJobContext
from app.research.research_job_stages import (
    collect_evidence_for_job,
    decide_job_outcome,
)

logger = get_logger(__name__)

EmbedQuery = Callable[[str], list[float]]
WebResearchHook = Callable[..., Awaitable[str | None]]


async def run_research_job(
    *,
    job_id: uuid.UUID,
    db_factory,
    evidence_index,
    embed_query: EmbedQuery,
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
    except Exception:
        logger.exception("research.job_failed", job_id=str(job_id))
        job_session.fail_execution()
    finally:
        job_session.close()
