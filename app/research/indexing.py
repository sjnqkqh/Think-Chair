from collections.abc import Callable
from pathlib import Path

from langchain_core.embeddings import Embeddings
from langchain_openai import OpenAIEmbeddings
from sqlalchemy.orm import Session

from app.core.config import settings
from app.logging import get_logger
from app.models.research import (
    ResearchJobStatus,
    ResearchSource,
    ResearchSourceScope,
    ResearchSourceStatus,
)
from app.repositories import research_repo
from app.research.chunking import CHUNK_SCHEMA_VERSION, chunk_source, detect_language
from app.research.contracts import FetchedSource, IndexRequest, IndexResult, SourceChunk
from app.research.vector_store import ResearchVectorStore
from app.services.storage.base import FileStorage

EMBEDDING_MODEL = "text-embedding-3-small"
EMBEDDING_DIMENSION = 1536
logger = get_logger(__name__)


def create_embedding_client(api_key: str | None = None) -> OpenAIEmbeddings:
    return OpenAIEmbeddings(
        api_key=api_key or settings.OPENAI_API_KEY,
        model=EMBEDDING_MODEL,
        dimensions=EMBEDDING_DIMENSION,
    )


def create_vector_store(path: Path | None = None) -> ResearchVectorStore:
    return ResearchVectorStore(
        path or settings.CHROMA_ROOT,
        embedding_model=EMBEDDING_MODEL,
        embedding_dimension=EMBEDDING_DIMENSION,
        chunk_schema_version=CHUNK_SCHEMA_VERSION,
    )


def _scope(value: str | None) -> ResearchSourceScope | None:
    try:
        return ResearchSourceScope(value) if value else None
    except ValueError:
        return None


def _metadata(
    chunk: SourceChunk,
    source: ResearchSource,
) -> dict[str, str | int]:
    metadata: dict[str, str | int] = {
        "chunk_id": chunk.id,
        "source_id": str(source.id),
        "canonical_url": source.canonical_url,
        "source_url": chunk.source_url,
        "content_hash": source.content_hash,
        "language": chunk.language,
        "section_kind": chunk.section_kind,
        "ordinal": chunk.ordinal,
        "start_index": chunk.start_index,
        "embedding_model": source.embedding_model,
        "embedding_dimension": source.embedding_dimension,
        "chunk_schema_version": source.chunk_schema_version,
    }
    if source.scope == ResearchSourceScope.PRIVATE:
        metadata["owner_user_id"] = str(source.owner_user_id)
        metadata["owner_manuscript_id"] = str(source.owner_manuscript_id)
    return metadata


async def index_sources(
    request: IndexRequest,
    *,
    db: Session,
    storage: FileStorage,
    embeddings: Embeddings,
    vector_store: ResearchVectorStore,
    admit_source: Callable[[FetchedSource], str | None],
) -> IndexResult:
    job = research_repo.get_owned_job(
        db,
        request.research_job_id,
        request.user_id,
        request.manuscript_id,
    )
    if job is None:
        return IndexResult(status="failed", error_codes=["job_not_found"])

    job.status = ResearchJobStatus.RUNNING
    job.terminal_error = None
    db.commit()

    indexed_source_ids = []
    skipped_source_keys = []
    error_codes = []
    chunk_count = 0

    for fetched_source in request.sources:
        scope = _scope(admit_source(fetched_source))
        if scope is None:
            skipped_source_keys.append(fetched_source.source_key)
            continue

        source = research_repo.find_source_by_url(
            db,
            scope,
            fetched_source.requested_url,
            request.user_id,
            request.manuscript_id,
        ) or research_repo.find_source_by_url(
            db,
            scope,
            fetched_source.canonical_url,
            request.user_id,
            request.manuscript_id,
        )

        if source is not None and source.status == ResearchSourceStatus.TOMBSTONED:
            skipped_source_keys.append(fetched_source.source_key)
            continue

        if source is not None and source.status == ResearchSourceStatus.INDEXED:
            research_repo.add_url_alias(
                db,
                source,
                fetched_source.requested_url,
                request.user_id,
                request.manuscript_id,
                is_canonical=False,
            )
            research_repo.attach_source_to_job(db, job, source)
            db.commit()
            if source.id not in indexed_source_ids:
                indexed_source_ids.append(source.id)
            skipped_source_keys.append(fetched_source.source_key)
            continue

        if source is None:
            identity_key = research_repo.scoped_identity(
                scope,
                fetched_source.canonical_url,
                request.user_id,
                request.manuscript_id,
            )
            source_id = research_repo.deterministic_source_id(identity_key)
            source = ResearchSource(
                id=source_id,
                identity_key=identity_key,
                scope=scope,
                owner_user_id=(
                    request.user_id if scope == ResearchSourceScope.PRIVATE else None
                ),
                owner_manuscript_id=(
                    request.manuscript_id
                    if scope == ResearchSourceScope.PRIVATE
                    else None
                ),
                canonical_url=fetched_source.canonical_url,
                title=fetched_source.title,
                publisher=fetched_source.publisher,
                published_at=fetched_source.published_at,
                fetched_at=fetched_source.fetched_at,
                content_hash=fetched_source.content_hash,
                storage_key=f"research_sources/{source_id}.json",
                language=detect_language(
                    "\n".join(
                        [fetched_source.text]
                        + [section.text for section in fetched_source.sections]
                    )
                ),
                status=ResearchSourceStatus.PENDING,
                embedding_model=vector_store.contract["embedding_model"],
                embedding_dimension=vector_store.contract["embedding_dimension"],
                chunk_schema_version=vector_store.contract["chunk_schema_version"],
            )
            db.add(source)
        else:
            source.status = ResearchSourceStatus.PENDING
            source.content_hash = fetched_source.content_hash

        research_repo.add_url_alias(
            db,
            source,
            fetched_source.canonical_url,
            request.user_id,
            request.manuscript_id,
            is_canonical=True,
        )
        research_repo.add_url_alias(
            db,
            source,
            fetched_source.requested_url,
            request.user_id,
            request.manuscript_id,
            is_canonical=fetched_source.requested_url == fetched_source.canonical_url,
        )
        db.commit()

        chunks = chunk_source(
            fetched_source,
            source.id,
            chunk_schema_version=source.chunk_schema_version,
        )
        chunk_ids = [chunk.id for chunk in chunks]
        try:
            storage.save(
                source.storage_key,
                fetched_source.model_dump_json().encode("utf-8"),
            )
            vectors = await embeddings.aembed_documents(
                [chunk.text for chunk in chunks]
            )
            vector_store.upsert(
                scope=scope.value,
                ids=chunk_ids,
                documents=[chunk.text for chunk in chunks],
                embeddings=vectors,
                metadatas=[_metadata(chunk, source) for chunk in chunks],
            )
        except Exception:
            logger.exception("research.source_index_failed", source_id=str(source.id))
            cleanup_failed = False
            try:
                vector_store.delete(scope.value, chunk_ids)
            except Exception:
                cleanup_failed = True
                logger.exception(
                    "research.vector_cleanup_failed", source_id=str(source.id)
                )
            try:
                storage.delete(source.storage_key)
            except Exception:
                cleanup_failed = True
                logger.exception(
                    "research.raw_source_cleanup_failed", source_id=str(source.id)
                )
            source.status = ResearchSourceStatus.FAILED
            db.commit()
            error_codes.append(
                "source_cleanup_failed" if cleanup_failed else "source_index_failed"
            )
            continue

        source.status = ResearchSourceStatus.INDEXED
        research_repo.attach_source_to_job(db, job, source)
        db.commit()
        indexed_source_ids.append(source.id)
        chunk_count += len(chunks)

    if error_codes:
        status = "partial" if indexed_source_ids else "failed"
    else:
        status = "completed"
    job.status = ResearchJobStatus(status)
    job.terminal_error = error_codes[0] if status == "failed" else None
    db.commit()
    return IndexResult(
        indexed_source_ids=indexed_source_ids,
        chunk_count=chunk_count,
        skipped_source_keys=skipped_source_keys,
        error_codes=error_codes,
        status=status,
    )
