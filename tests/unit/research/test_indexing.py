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
    ResearchIndexRequest,
)
from app.research.evidence_index import ResearchEvidenceIndex
from app.research.indexing import (
    create_research_embeddings,
    create_research_evidence_index,
    index_research_sources,
)
from app.research.source_chunking import CHUNK_OVERLAP, CHUNK_SIZE
from app.research.source_exclusion import exclude_source_from_corpus
from app.services.storage.local import LocalFileStorage


def _create_user_and_manuscript(db_session, suffix: str):
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


def _create_research_job(db_session, user: User, manuscript: Manuscript):
    job = ResearchJob(user_id=user.id, manuscript_id=manuscript.id)
    db_session.add(job)
    db_session.commit()
    return job


def _make_fetched_source(
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
    monkeypatch.setattr(
        "app.research.source_chunking._retrieval_text_splitter",
        lambda: splitter,
    )


async def _index_request(
    db_session,
    tmp_path,
    request: ResearchIndexRequest,
    *,
    scope: str,
    embeddings=None,
    evidence_index=None,
):
    return await index_research_sources(
        request,
        db=db_session,
        storage=LocalFileStorage(tmp_path / "storage"),
        embeddings=embeddings or DeterministicFakeEmbedding(size=8),
        evidence_index=evidence_index
        or ResearchEvidenceIndex(
            f"sqlite:///{tmp_path / 'evidence.db'}",
            embedding_model="test-model",
            embedding_dimension=8,
            chunk_schema_version="chunk-600-100-v1",
        ),
        admit_source=lambda source: scope,
    )


def _count_indexed_chunks(
    evidence_index: ResearchEvidenceIndex, scope: str
) -> int:
    return evidence_index.count_chunks(scope)


async def test_reuses_public_source_and_adds_redirect_alias(db_session, tmp_path):
    """같은 대표 URL의 공개 자료는 사용자와 요청 URL이 달라도 벡터를 복제하지 않는지 검증한다."""
    first_user, first_manuscript = _create_user_and_manuscript(db_session, "first")
    second_user, second_manuscript = _create_user_and_manuscript(
        db_session, "second"
    )
    first_job = _create_research_job(db_session, first_user, first_manuscript)
    second_job = _create_research_job(db_session, second_user, second_manuscript)
    evidence_index = ResearchEvidenceIndex(
        f"sqlite:///{tmp_path / 'evidence.db'}",
        embedding_model="test-model",
        embedding_dimension=8,
        chunk_schema_version="chunk-600-100-v1",
    )

    first = await _index_request(
        db_session,
        tmp_path,
        ResearchIndexRequest(
            research_job_id=first_job.id,
            user_id=first_user.id,
            manuscript_id=first_manuscript.id,
            sources=[_make_fetched_source()],
        ),
        scope="public",
        evidence_index=evidence_index,
    )
    original_count = _count_indexed_chunks(evidence_index, "public")
    second = await _index_request(
        db_session,
        tmp_path,
        ResearchIndexRequest(
            research_job_id=second_job.id,
            user_id=second_user.id,
            manuscript_id=second_manuscript.id,
            sources=[
                _make_fetched_source(
                    requested_url="https://example.com/redirect"
                )
            ],
        ),
        scope="public",
        evidence_index=evidence_index,
    )

    assert first.status == "completed"
    assert second.status == "completed"
    assert second.chunk_count == 0
    assert _count_indexed_chunks(evidence_index, "public") == original_count
    assert db_session.query(ResearchSource).count() == 1
    assert second.skipped_source_keys == ["source-key"]
    metadata = evidence_index.list_metadatas("public")
    assert all(
        item["canonical_url"] == _make_fetched_source().canonical_url
        for item in metadata
    )
    assert any(item["source_url"].endswith("#comment-1") for item in metadata)


async def test_indexes_source_when_requested_url_matches_canonical(db_session, tmp_path):
    """요청 URL과 canonical URL이 같아도 URL alias UNIQUE 충돌 없이 인덱싱한다."""
    user, manuscript = _create_user_and_manuscript(db_session, "same-url")
    job = _create_research_job(db_session, user, manuscript)
    evidence_index = ResearchEvidenceIndex(
        f"sqlite:///{tmp_path / 'evidence_same_url.db'}",
        embedding_model="test-model",
        embedding_dimension=8,
        chunk_schema_version="chunk-600-100-v1",
    )
    url = "https://example.com/same-url"
    result = await _index_request(
        db_session,
        tmp_path,
        ResearchIndexRequest(
            research_job_id=job.id,
            user_id=user.id,
            manuscript_id=manuscript.id,
            sources=[
                _make_fetched_source(
                    requested_url=url,
                    canonical_url=url,
                )
            ],
        ),
        scope="public",
        evidence_index=evidence_index,
    )

    assert result.status == "completed"
    assert result.chunk_count > 0
    assert db_session.query(ResearchSource).count() == 1
    assert db_session.query(ResearchSourceUrl).count() == 1


async def test_isolates_private_sources_by_owner_and_manuscript(db_session, tmp_path):
    """같은 URL의 비공개 자료도 다른 사용자·원고 사이에서는 별도 자료로 저장하는지 검증한다."""
    first_user, first_manuscript = _create_user_and_manuscript(
        db_session, "private-first"
    )
    second_user, second_manuscript = _create_user_and_manuscript(
        db_session, "private-second"
    )
    first_job = _create_research_job(db_session, first_user, first_manuscript)
    second_job = _create_research_job(db_session, second_user, second_manuscript)
    evidence_index = ResearchEvidenceIndex(
        f"sqlite:///{tmp_path / 'evidence.db'}",
        embedding_model="test-model",
        embedding_dimension=8,
        chunk_schema_version="chunk-600-100-v1",
    )

    for job, user, manuscript in [
        (first_job, first_user, first_manuscript),
        (second_job, second_user, second_manuscript),
    ]:
        result = await _index_request(
            db_session,
            tmp_path,
            ResearchIndexRequest(
                research_job_id=job.id,
                user_id=user.id,
                manuscript_id=manuscript.id,
                sources=[_make_fetched_source()],
            ),
            scope="private",
            evidence_index=evidence_index,
        )
        assert result.status == "completed"

    assert db_session.query(ResearchSource).count() == 2
    assert _count_indexed_chunks(evidence_index, "private") > 1
    assert _count_indexed_chunks(evidence_index, "public") == 0


async def test_rejects_job_owned_by_another_user(db_session, tmp_path):
    """다른 사용자의 조사 작업 ID로 자료를 저장해 비공개 범위를 우회하지 못하는지 검증한다."""
    owner, owner_manuscript = _create_user_and_manuscript(db_session, "owner")
    stranger, stranger_manuscript = _create_user_and_manuscript(
        db_session, "stranger"
    )
    job = _create_research_job(db_session, owner, owner_manuscript)

    result = await _index_request(
        db_session,
        tmp_path,
        ResearchIndexRequest(
            research_job_id=job.id,
            user_id=stranger.id,
            manuscript_id=stranger_manuscript.id,
            sources=[_make_fetched_source()],
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
    user, manuscript = _create_user_and_manuscript(db_session, "retry")
    job = _create_research_job(db_session, user, manuscript)
    request = ResearchIndexRequest(
        research_job_id=job.id,
        user_id=user.id,
        manuscript_id=manuscript.id,
        sources=[_make_fetched_source()],
    )
    evidence_index = ResearchEvidenceIndex(
        f"sqlite:///{tmp_path / 'evidence.db'}",
        embedding_model="test-model",
        embedding_dimension=8,
        chunk_schema_version="chunk-600-100-v1",
    )
    embeddings = _FailOnceEmbeddings(size=8)

    failed = await _index_request(
        db_session,
        tmp_path,
        request,
        scope="public",
        embeddings=embeddings,
        evidence_index=evidence_index,
    )
    source = db_session.query(ResearchSource).one()

    assert failed.status == "failed"
    assert source.status == ResearchSourceStatus.FAILED
    assert _count_indexed_chunks(evidence_index, "public") == 0
    assert not (tmp_path / "storage" / source.storage_key).exists()

    completed = await _index_request(
        db_session,
        tmp_path,
        request,
        scope="public",
        embeddings=embeddings,
        evidence_index=evidence_index,
    )

    assert completed.status == "completed"
    assert db_session.query(ResearchSource).count() == 1
    assert (
        _count_indexed_chunks(evidence_index, "public")
        == completed.chunk_count
    )


async def test_reports_partial_when_only_some_sources_are_indexed(
    db_session, tmp_path
):
    """여러 자료 중 일부만 실패하면 성공 자료를 보존하고 작업 상태를 partial로 남기는지 검증한다."""
    user, manuscript = _create_user_and_manuscript(db_session, "partial")
    job = _create_research_job(db_session, user, manuscript)

    result = await _index_request(
        db_session,
        tmp_path,
        ResearchIndexRequest(
            research_job_id=job.id,
            user_id=user.id,
            manuscript_id=manuscript.id,
            sources=[
                _make_fetched_source(canonical_url="https://example.com/first"),
                _make_fetched_source(canonical_url="https://example.com/second"),
            ],
        ),
        scope="public",
        embeddings=_FailOnceEmbeddings(size=8),
    )

    assert result.status == "partial"
    assert result.error_codes == ["source_index_failed"]
    assert len(result.indexed_source_ids) == 1
    assert result.chunk_count > 0


async def test_does_not_restore_excluded_source(db_session, tmp_path):
    """정책 위반으로 제외한 자료는 같은 URL이 다시 들어와도 원문과 벡터를 복원하지 않는지 검증한다."""
    user, manuscript = _create_user_and_manuscript(db_session, "excluded")
    job = _create_research_job(db_session, user, manuscript)
    request = ResearchIndexRequest(
        research_job_id=job.id,
        user_id=user.id,
        manuscript_id=manuscript.id,
        sources=[_make_fetched_source()],
    )
    evidence_index = ResearchEvidenceIndex(
        f"sqlite:///{tmp_path / 'evidence.db'}",
        embedding_model="test-model",
        embedding_dimension=8,
        chunk_schema_version="chunk-600-100-v1",
    )
    await _index_request(
        db_session,
        tmp_path,
        request,
        scope="public",
        evidence_index=evidence_index,
    )
    source = db_session.query(ResearchSource).one()
    storage = LocalFileStorage(tmp_path / "storage")

    exclude_source_from_corpus(
        source.id,
        db=db_session,
        storage=storage,
        evidence_index=evidence_index,
    )

    assert _count_indexed_chunks(evidence_index, "public") == 0
    assert not (tmp_path / "storage" / source.storage_key).exists()

    result = await _index_request(
        db_session,
        tmp_path,
        request,
        scope="public",
        embeddings=_FailOnceEmbeddings(size=8, failed=True),
        evidence_index=evidence_index,
    )

    assert result.status == "completed"
    assert result.chunk_count == 0
    assert result.skipped_source_keys == ["source-key"]
    assert source.status == ResearchSourceStatus.EXCLUDED


def test_builds_the_selected_embeddings_and_evidence_index(tmp_path):
    """실제 색인 조립에서 합의한 OpenAI 모델·차원·Chroma 계약을 사용하도록 고정하는지 검증한다."""
    embeddings = create_research_embeddings("test-key")
    evidence_index = create_research_evidence_index(f"sqlite:///{tmp_path / 'evidence.db'}")

    assert embeddings.model == "text-embedding-3-small"
    assert embeddings.dimensions == 1536
    assert evidence_index.index_contract == {
        "embedding_model": "text-embedding-3-small",
        "embedding_dimension": 1536,
        "chunk_schema_version": "chunk-600-100-v1",
    }
