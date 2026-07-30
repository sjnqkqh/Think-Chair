from datetime import datetime, timezone

import pytest
from langchain_core.embeddings import DeterministicFakeEmbedding
from langchain_text_splitters import RecursiveCharacterTextSplitter

from app.models.manuscript import ConceptType, Manuscript
from app.models.research import (
    ResearchJob,
    ResearchJobSource,
    ResearchSource,
    ResearchSourceStatus,
    ResearchSourceUrl,
)
from app.models.user import User
from app.research.contracts import (
    ExtractedSection,
    FetchedSource,
    IndexRequest,
)
from app.research.chunking import CHUNK_OVERLAP, CHUNK_SIZE
from app.research.indexing import (
    create_embedding_client,
    create_vector_store,
    index_sources,
)
from app.research.corpus import tombstone_source
from app.research.vector_store import ResearchVectorStore
from app.services.storage.local import LocalFileStorage


def _user_and_manuscript(db_session, suffix: str):
    user = User(
        login_id=f"user-{suffix}",
        password_hash="hash",
        nickname=f"사용자 {suffix}",
    )
    db_session.add(user)
    db_session.flush()
    manuscript = Manuscript(
        user_id=user.id,
        topic=f"주제 {suffix}",
        concept=ConceptType.TECH_DEEPDIVE,
    )
    db_session.add(manuscript)
    db_session.flush()
    return user, manuscript


def _job(db_session, user: User, manuscript: Manuscript):
    job = ResearchJob(user_id=user.id, manuscript_id=manuscript.id)
    db_session.add(job)
    db_session.commit()
    return job


def _source(
    *,
    requested_url: str = "https://example.com/requested",
    canonical_url: str = "https://example.com/canonical",
):
    return FetchedSource(
        requested_url=requested_url,
        canonical_url=canonical_url,
        title="공식 문서",
        publisher="Example",
        published_at="2026-07-01",
        text="큐의 처리량과 지연 시간에 관한 충분히 긴 공식 설명입니다. " * 30,
        sections=[
            ExtractedSection(
                kind="comment",
                text="실무에서 관찰한 추가 사례입니다.",
                permalink=f"{canonical_url}#comment-1",
            )
        ],
        media_type="text/html",
        fetched_at=datetime.now(timezone.utc),
        content_hash="content-hash",
        source_key="source-key",
    )


@pytest.fixture(autouse=True)
def isolated_research_state(db_session, monkeypatch):
    for model in (ResearchJobSource, ResearchSourceUrl, ResearchSource, ResearchJob):
        db_session.query(model).delete()
    db_session.commit()
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=CHUNK_SIZE,
        chunk_overlap=CHUNK_OVERLAP,
        length_function=len,
        separators=["\n\n", "\n", "。", ". ", " ", ""],
        keep_separator="end",
        add_start_index=True,
    )
    monkeypatch.setattr("app.research.chunking._splitter", lambda: splitter)


async def _index(
    db_session,
    tmp_path,
    request: IndexRequest,
    *,
    scope: str,
    embeddings=None,
    vector_store=None,
):
    return await index_sources(
        request,
        db=db_session,
        storage=LocalFileStorage(tmp_path / "storage"),
        embeddings=embeddings or DeterministicFakeEmbedding(size=8),
        vector_store=vector_store
        or ResearchVectorStore(
            tmp_path / "chroma_db",
            embedding_model="test-model",
            embedding_dimension=8,
            chunk_schema_version="chunk-600-100-v1",
        ),
        admit_source=lambda source: scope,
    )


async def test_reuses_public_source_and_adds_redirect_alias(db_session, tmp_path):
    """같은 대표 URL의 공개 자료는 사용자와 요청 URL이 달라도 벡터를 복제하지 않는지 검증한다."""
    first_user, first_manuscript = _user_and_manuscript(db_session, "first")
    second_user, second_manuscript = _user_and_manuscript(db_session, "second")
    first_job = _job(db_session, first_user, first_manuscript)
    second_job = _job(db_session, second_user, second_manuscript)
    store = ResearchVectorStore(
        tmp_path / "chroma_db",
        embedding_model="test-model",
        embedding_dimension=8,
        chunk_schema_version="chunk-600-100-v1",
    )

    first = await _index(
        db_session,
        tmp_path,
        IndexRequest(
            research_job_id=first_job.id,
            user_id=first_user.id,
            manuscript_id=first_manuscript.id,
            sources=[_source()],
        ),
        scope="public",
        vector_store=store,
    )
    original_count = store.count("public")
    second = await _index(
        db_session,
        tmp_path,
        IndexRequest(
            research_job_id=second_job.id,
            user_id=second_user.id,
            manuscript_id=second_manuscript.id,
            sources=[_source(requested_url="https://example.com/redirect")],
        ),
        scope="public",
        vector_store=store,
    )

    assert first.status == "completed"
    assert second.status == "completed"
    assert second.chunk_count == 0
    assert store.count("public") == original_count
    assert db_session.query(ResearchSource).count() == 1
    assert second.skipped_source_keys == ["source-key"]
    metadata = store.get("public")["metadatas"]
    assert all(item["canonical_url"] == _source().canonical_url for item in metadata)
    assert any(item["source_url"].endswith("#comment-1") for item in metadata)


async def test_isolates_private_sources_by_owner_and_manuscript(db_session, tmp_path):
    """같은 URL의 비공개 자료도 다른 사용자·원고 사이에서는 별도 자료로 저장하는지 검증한다."""
    first_user, first_manuscript = _user_and_manuscript(db_session, "private-first")
    second_user, second_manuscript = _user_and_manuscript(db_session, "private-second")
    first_job = _job(db_session, first_user, first_manuscript)
    second_job = _job(db_session, second_user, second_manuscript)
    store = ResearchVectorStore(
        tmp_path / "chroma_db",
        embedding_model="test-model",
        embedding_dimension=8,
        chunk_schema_version="chunk-600-100-v1",
    )

    for job, user, manuscript in [
        (first_job, first_user, first_manuscript),
        (second_job, second_user, second_manuscript),
    ]:
        result = await _index(
            db_session,
            tmp_path,
            IndexRequest(
                research_job_id=job.id,
                user_id=user.id,
                manuscript_id=manuscript.id,
                sources=[_source()],
            ),
            scope="private",
            vector_store=store,
        )
        assert result.status == "completed"

    assert db_session.query(ResearchSource).count() == 2
    assert store.count("private") > 1
    assert store.count("public") == 0


async def test_rejects_job_owned_by_another_user(db_session, tmp_path):
    """다른 사용자의 조사 작업 ID로 자료를 저장해 비공개 범위를 우회하지 못하는지 검증한다."""
    owner, owner_manuscript = _user_and_manuscript(db_session, "owner")
    stranger, stranger_manuscript = _user_and_manuscript(db_session, "stranger")
    job = _job(db_session, owner, owner_manuscript)

    result = await _index(
        db_session,
        tmp_path,
        IndexRequest(
            research_job_id=job.id,
            user_id=stranger.id,
            manuscript_id=stranger_manuscript.id,
            sources=[_source()],
        ),
        scope="private",
    )

    assert result.status == "failed"
    assert result.error_codes == ["job_not_found"]
    assert db_session.query(ResearchSource).count() == 0


class _FailOnceEmbeddings(DeterministicFakeEmbedding):
    failed: bool = False

    async def aembed_documents(self, texts):
        if not self.failed:
            self.failed = True
            raise RuntimeError("temporary embedding failure")
        return await super().aembed_documents(texts)


async def test_cleans_failed_artifacts_and_retries_without_duplicates(
    db_session, tmp_path
):
    """임베딩 실패 산출물을 정리하고 같은 자료 재시도에서 중복 없이 성공하는지 검증한다."""
    user, manuscript = _user_and_manuscript(db_session, "retry")
    job = _job(db_session, user, manuscript)
    request = IndexRequest(
        research_job_id=job.id,
        user_id=user.id,
        manuscript_id=manuscript.id,
        sources=[_source()],
    )
    store = ResearchVectorStore(
        tmp_path / "chroma_db",
        embedding_model="test-model",
        embedding_dimension=8,
        chunk_schema_version="chunk-600-100-v1",
    )
    embeddings = _FailOnceEmbeddings(size=8)

    failed = await _index(
        db_session,
        tmp_path,
        request,
        scope="public",
        embeddings=embeddings,
        vector_store=store,
    )
    source = db_session.query(ResearchSource).one()

    assert failed.status == "failed"
    assert source.status == ResearchSourceStatus.FAILED
    assert store.count("public") == 0
    assert not (tmp_path / "storage" / source.storage_key).exists()

    completed = await _index(
        db_session,
        tmp_path,
        request,
        scope="public",
        embeddings=embeddings,
        vector_store=store,
    )

    assert completed.status == "completed"
    assert db_session.query(ResearchSource).count() == 1
    assert store.count("public") == completed.chunk_count


async def test_reports_partial_when_only_some_sources_are_indexed(
    db_session, tmp_path
):
    """여러 자료 중 일부만 실패하면 성공 자료를 보존하고 작업 상태를 partial로 남기는지 검증한다."""
    user, manuscript = _user_and_manuscript(db_session, "partial")
    job = _job(db_session, user, manuscript)

    result = await _index(
        db_session,
        tmp_path,
        IndexRequest(
            research_job_id=job.id,
            user_id=user.id,
            manuscript_id=manuscript.id,
            sources=[
                _source(canonical_url="https://example.com/first"),
                _source(canonical_url="https://example.com/second"),
            ],
        ),
        scope="public",
        embeddings=_FailOnceEmbeddings(size=8),
    )

    assert result.status == "partial"
    assert result.error_codes == ["source_index_failed"]
    assert len(result.indexed_source_ids) == 1
    assert result.chunk_count > 0


async def test_does_not_restore_tombstoned_source(db_session, tmp_path):
    """정책 위반으로 제외한 자료는 같은 URL이 다시 들어와도 원문과 벡터를 복원하지 않는지 검증한다."""
    user, manuscript = _user_and_manuscript(db_session, "tombstoned")
    job = _job(db_session, user, manuscript)
    request = IndexRequest(
        research_job_id=job.id,
        user_id=user.id,
        manuscript_id=manuscript.id,
        sources=[_source()],
    )
    store = ResearchVectorStore(
        tmp_path / "chroma_db",
        embedding_model="test-model",
        embedding_dimension=8,
        chunk_schema_version="chunk-600-100-v1",
    )
    await _index(
        db_session,
        tmp_path,
        request,
        scope="public",
        vector_store=store,
    )
    source = db_session.query(ResearchSource).one()
    storage = LocalFileStorage(tmp_path / "storage")

    tombstone_source(
        source.id,
        db=db_session,
        storage=storage,
        vector_store=store,
    )

    assert store.count("public") == 0
    assert not (tmp_path / "storage" / source.storage_key).exists()

    result = await _index(
        db_session,
        tmp_path,
        request,
        scope="public",
        embeddings=_FailOnceEmbeddings(size=8, failed=True),
        vector_store=store,
    )

    assert result.status == "completed"
    assert result.chunk_count == 0
    assert result.skipped_source_keys == ["source-key"]
    assert source.status == ResearchSourceStatus.TOMBSTONED


def test_builds_the_selected_embedding_and_vector_store(tmp_path):
    """실제 색인 조립에서 합의한 OpenAI 모델·차원·Chroma 계약을 사용하도록 고정하는지 검증한다."""
    client = create_embedding_client("test-key")
    store = create_vector_store(tmp_path / "chroma_db")

    assert client.model == "text-embedding-3-small"
    assert client.dimensions == 1536
    assert store.contract == {
        "embedding_model": "text-embedding-3-small",
        "embedding_dimension": 1536,
        "chunk_schema_version": "chunk-600-100-v1",
    }
