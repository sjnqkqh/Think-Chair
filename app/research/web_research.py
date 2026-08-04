"""인덱스 근거가 부족할 때 웹 검색·수집·인덱싱으로 자료를 넓힌다."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from app.logging import get_logger
from app.research.contracts import (
    FetchRequest,
    FetchedSource,
    ResearchIndexRequest,
    SearchRequest,
)

logger = get_logger(__name__)

AdmitSource = Callable[[FetchedSource], str | None]
SearchWeb = Callable[..., Awaitable[Any]]
FetchPage = Callable[..., Awaitable[Any]]
IndexResearchSources = Callable[..., Awaitable[Any]]


async def expand_evidence_via_web_search(
    *,
    db,
    job,
    query: str,
    evidence_index,
    storage,
    embeddings,
    search_web: SearchWeb,
    fetch_page: FetchPage,
    index_research_sources: IndexResearchSources,
    admit_source: AdmitSource,
    max_fetches: int = 3,
) -> str | None:
    """웹 검색·수집·인덱싱. 성공하면 None, 실패하면 error_code를 반환한다."""
    search_response = await search_web(SearchRequest(query=query, max_results=max_fetches))
    if search_response.error_code or not search_response.results:
        error_code = search_response.error_code or "search_empty"
        logger.info(
            "research.web_search_empty",
            job_id=str(job.id),
            error_code=error_code,
        )
        return error_code

    fetched_sources: list[FetchedSource] = []
    for hit in search_response.results[:max_fetches]:
        try:
            fetch_response = await fetch_page(FetchRequest(url=hit.url))
        except Exception:
            logger.exception(
                "research.fetch_raised",
                job_id=str(job.id),
                url=hit.url,
            )
            continue
        if fetch_response.source is None:
            logger.info(
                "research.fetch_skipped",
                job_id=str(job.id),
                url=hit.url,
                error_code=fetch_response.error_code,
            )
            continue
        fetched_sources.append(fetch_response.source)

    if not fetched_sources:
        return "fetch_all_failed"

    await index_research_sources(
        ResearchIndexRequest(
            research_job_id=job.id,
            user_id=job.user_id,
            manuscript_id=job.manuscript_id,
            sources=fetched_sources,
        ),
        db=db,
        storage=storage,
        embeddings=embeddings,
        evidence_index=evidence_index,
        admit_source=admit_source,
    )
    return None
