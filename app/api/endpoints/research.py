import uuid

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.auth_deps import require_user
from app.core.config import settings
from app.core.database import get_database_session
from app.core.storage import get_file_storage
from app.models.user import User
from app.research.indexing import (
    create_research_embeddings,
    create_research_evidence_index,
    index_research_sources,
)
from app.research.page_fetcher import fetch_page
from app.research.research_job_runner import run_research_job
from app.research.web_research import expand_evidence_via_web_search
from app.research.web_search import search_web
from app.services.manuscript_service import get_manuscript
from app.services.research_job_service import (
    create_or_get_research_job,
    get_owned_research_job,
    mark_job_cancelled,
)

router = APIRouter(prefix="/api/research", tags=["research"])


class CreateResearchJobBody(BaseModel):
    manuscript_id: uuid.UUID
    message_id: uuid.UUID
    claim_or_query: str = Field(min_length=1)


@router.post("/jobs", status_code=202)
async def create_research_job(
    request: Request,
    body: CreateResearchJobBody,
    user: User = Depends(require_user),
    database_session: Session = Depends(get_database_session),
):
    manuscript = get_manuscript(database_session, user, body.manuscript_id)
    chat_service = request.app.state.chat_service

    async def _run(job_id: uuid.UUID):
        embeddings = create_research_embeddings()
        evidence_index = create_research_evidence_index()
        storage = get_file_storage()

        async def web_research(*, db, job, query, evidence_index):
            await expand_evidence_via_web_search(
                db=db,
                job=job,
                query=query,
                evidence_index=evidence_index,
                storage=storage,
                embeddings=embeddings,
                search_web=search_web,
                fetch_page=fetch_page,
                index_research_sources=index_research_sources,
                admit_source=lambda _source: "public",
            )

        await run_research_job(
            job_id=job_id,
            db_factory=chat_service.db_factory,
            evidence_index=evidence_index,
            embed_query=embeddings.embed_query,
            generate_invoke=_make_invoker(
                settings.RESPONSE_COMPARISON_GENERATION_MODEL
            ),
            judge_invoke=_make_invoker(settings.RESPONSE_COMPARISON_JUDGE_MODEL),
            generation_model=settings.RESPONSE_COMPARISON_GENERATION_MODEL,
            judge_model=settings.RESPONSE_COMPARISON_JUDGE_MODEL,
            web_research=web_research,
        )

    job, created = create_or_get_research_job(
        database_session,
        user_id=user.id,
        manuscript_id=manuscript.id,
        message_id=body.message_id,
        claim_or_query=body.claim_or_query,
        background_tasks=chat_service.background_tasks,
        run_job=_run,
    )
    return {
        "id": str(job.id),
        "status": job.status.value,
        "created": created,
        "status_url": f"/api/research/jobs/{job.id}",
    }


@router.get("/jobs/{job_id}")
async def get_research_job(
    job_id: uuid.UUID,
    manuscript_id: uuid.UUID,
    user: User = Depends(require_user),
    database_session: Session = Depends(get_database_session),
):
    get_manuscript(database_session, user, manuscript_id)
    job = get_owned_research_job(
        database_session,
        job_id=job_id,
        user_id=user.id,
        manuscript_id=manuscript_id,
    )
    if job is None:
        return {"error": "not_found"}
    ready = job.status.value in {"completed", "partial"}
    return {
        "id": str(job.id),
        "status": job.status.value,
        "terminal_error": job.terminal_error,
        "evidence_ready": ready,
    }


@router.post("/jobs/{job_id}/cancel")
async def cancel_research_job(
    job_id: uuid.UUID,
    manuscript_id: uuid.UUID,
    user: User = Depends(require_user),
    database_session: Session = Depends(get_database_session),
):
    get_manuscript(database_session, user, manuscript_id)
    job = get_owned_research_job(
        database_session,
        job_id=job_id,
        user_id=user.id,
        manuscript_id=manuscript_id,
    )
    if job is None:
        return {"error": "not_found"}
    job = mark_job_cancelled(database_session, job)
    return {"id": str(job.id), "status": job.status.value}


def _make_invoker(model_name: str):
    from langchain_openai import ChatOpenAI

    api_key = settings.RESPONSE_COMPARISON_API_KEY or settings.OPENAI_API_KEY
    language_model = ChatOpenAI(
        api_key=api_key,
        base_url=settings.RESPONSE_COMPARISON_API_BASE,
        model=model_name,
        temperature=0,
    )

    def invoke(prompt: str) -> str:
        message = language_model.invoke(prompt)
        content = message.content
        if isinstance(content, list):
            return "".join(
                part.get("text", "") if isinstance(part, dict) else str(part)
                for part in content
            )
        return str(content)

    return invoke
