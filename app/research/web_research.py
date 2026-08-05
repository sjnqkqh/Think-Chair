"""인덱스 근거가 부족할 때 웹 검색·수집·인덱싱으로 자료를 넓힌다."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from app.evaluation.text_parsing import strip_code_fence
from app.logging import get_logger
from app.repositories import research_repo
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
PromptInvoker = Callable[[str], str]

_MAX_SEARCH_QUERY_CHARS = 400
_MAX_SEARCH_QUERY_WORDS = 50


def build_web_search_keyword_prompt(claim: str) -> str:
    return (
        "Convert the claim below into a short English web search query.\n"
        "Use only the essential keywords (about 5-12 words).\n"
        "Return only the query text on one line. No quotes, no explanation.\n\n"
        f"Claim:\n{claim.strip()}"
    )


def summarize_claim_as_web_search_query(
    claim: str, *, invoke: PromptInvoker
) -> str:
    """주장을 Brave 한도에 맞는 짧은 영어 검색 키워드로 요약한다."""
    raw = invoke(build_web_search_keyword_prompt(claim))
    text = strip_code_fence(raw).strip().strip('"').strip("'")
    if text:
        text = text.splitlines()[0].strip()
    words = text.split()
    if len(words) > _MAX_SEARCH_QUERY_WORDS:
        text = " ".join(words[:_MAX_SEARCH_QUERY_WORDS])
    if len(text) > _MAX_SEARCH_QUERY_CHARS:
        text = text[:_MAX_SEARCH_QUERY_CHARS].rstrip()
    return text


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
    summarize_query: PromptInvoker,
    max_fetches: int = 3,
) -> str | None:
    """웹 검색·수집·인덱싱. 성공하면 None, 실패하면 error_code를 반환한다."""
    search_query = summarize_claim_as_web_search_query(
        query, invoke=summarize_query
    )
    if not search_query:
        logger.info(
            "research.web_search_query_empty",
            job_id=str(job.id),
            claim_chars=len(query),
        )
        return "search_query_empty"

    logger.info(
        "research.web_search_query_summarized",
        job_id=str(job.id),
        claim_chars=len(query),
        search_query=search_query,
    )
    search_response = await search_web(
        SearchRequest(query=search_query, max_results=max_fetches)
    )
    research_repo.increment_research_search_count(
        db,
        user_id=job.user_id,
        manuscript_id=job.manuscript_id,
    )
    db.commit()
    if search_response.error_code or not search_response.results:
        error_code = search_response.error_code or "search_empty"
        logger.info(
            "research.web_search_empty",
            job_id=str(job.id),
            error_code=error_code,
        )
        return error_code

    logger.info(
        "research.web_search_completed",
        job_id=str(job.id),
        hit_count=len(search_response.results),
        max_fetches=max_fetches,
    )

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
        logger.info(
            "research.fetch_succeeded",
            job_id=str(job.id),
            url=hit.url,
            canonical_url=fetch_response.source.canonical_url,
        )
        fetched_sources.append(fetch_response.source)

    if not fetched_sources:
        return "fetch_all_failed"

    logger.info(
        "research.index_sources_requested",
        job_id=str(job.id),
        source_count=len(fetched_sources),
    )
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
