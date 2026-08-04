from __future__ import annotations

import datetime
import enum
import json
import uuid
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy import Enum as SAEnum
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base

if TYPE_CHECKING:
    from app.evaluation.response_comparison_contracts import (
        GeneratedResponse,
        PairwiseJudgment,
    )
    from app.research.contracts import FetchedSource, GroundedResponseResult


class ResearchJobStatus(str, enum.Enum):
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    PARTIAL = "partial"
    FAILED = "failed"
    CANCELLED = "cancelled"


class ResearchSourceScope(str, enum.Enum):
    PUBLIC = "public"
    PRIVATE = "private"


class ResearchSourceStatus(str, enum.Enum):
    PENDING = "pending"
    INDEXED = "indexed"
    FAILED = "failed"
    EXCLUDED = "excluded"


class ResearchJob(Base):
    __tablename__ = "research_jobs"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), index=True)
    manuscript_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("manuscripts.id"), index=True
    )
    message_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("chat_messages.id"), unique=True, nullable=True
    )
    claim_or_query: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[ResearchJobStatus] = mapped_column(
        SAEnum(ResearchJobStatus), default=ResearchJobStatus.QUEUED
    )
    terminal_error: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime, default=datetime.datetime.utcnow
    )
    updated_at: Mapped[datetime.datetime] = mapped_column(
        DateTime,
        default=datetime.datetime.utcnow,
        onupdate=datetime.datetime.utcnow,
    )

    def cancelled(self) -> bool:
        return self.status == ResearchJobStatus.CANCELLED

    def mark_running(self) -> None:
        self.status = ResearchJobStatus.RUNNING

    def mark_failed(self, terminal_error: str = "job_execution_error") -> None:
        self.status = ResearchJobStatus.FAILED
        self.terminal_error = terminal_error

    def mark_cancelled(self) -> bool:
        """이미 종료된 job이면 False. 아니면 CANCELLED로 바꾸고 True."""
        if self.status in {
            ResearchJobStatus.COMPLETED,
            ResearchJobStatus.PARTIAL,
            ResearchJobStatus.FAILED,
            ResearchJobStatus.CANCELLED,
        }:
            return False
        self.status = ResearchJobStatus.CANCELLED
        return True

    def mark_outcome(
        self,
        status: ResearchJobStatus,
        *,
        terminal_error: str | None = None,
    ) -> None:
        self.status = status
        self.terminal_error = terminal_error

    @classmethod
    def queued(
        cls,
        *,
        user_id: uuid.UUID,
        manuscript_id: uuid.UUID,
        message_id: uuid.UUID | None,
        claim_or_query: str | None,
    ) -> ResearchJob:
        return cls(
            user_id=user_id,
            manuscript_id=manuscript_id,
            message_id=message_id,
            claim_or_query=claim_or_query,
            status=ResearchJobStatus.QUEUED,
        )


class ResearchSource(Base):
    __tablename__ = "research_sources"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True)
    identity_key: Mapped[str] = mapped_column(String(64), unique=True)
    scope: Mapped[ResearchSourceScope] = mapped_column(SAEnum(ResearchSourceScope))
    owner_user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id"), nullable=True
    )
    owner_manuscript_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("manuscripts.id"), nullable=True
    )
    canonical_url: Mapped[str] = mapped_column(Text)
    title: Mapped[str] = mapped_column(Text)
    publisher: Mapped[str | None] = mapped_column(String(255), nullable=True)
    published_at: Mapped[str | None] = mapped_column(String(64), nullable=True)
    fetched_at: Mapped[datetime.datetime] = mapped_column(DateTime)
    content_hash: Mapped[str] = mapped_column(String(64))
    storage_key: Mapped[str] = mapped_column(String(255))
    language: Mapped[str] = mapped_column(String(16))
    status: Mapped[ResearchSourceStatus] = mapped_column(
        SAEnum(ResearchSourceStatus), default=ResearchSourceStatus.PENDING
    )
    embedding_model: Mapped[str] = mapped_column(String(128))
    embedding_dimension: Mapped[int] = mapped_column(Integer)
    chunk_schema_version: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime, default=datetime.datetime.utcnow
    )
    updated_at: Mapped[datetime.datetime] = mapped_column(
        DateTime,
        default=datetime.datetime.utcnow,
        onupdate=datetime.datetime.utcnow,
    )

    @classmethod
    def pending_from_fetch(
        cls,
        fetched: FetchedSource,
        *,
        scope: ResearchSourceScope,
        identity_key: str,
        source_id: uuid.UUID,
        user_id: uuid.UUID,
        manuscript_id: uuid.UUID,
        language: str,
        embedding_model: str,
        embedding_dimension: int,
        chunk_schema_version: str,
    ) -> ResearchSource:
        private = scope == ResearchSourceScope.PRIVATE
        return cls(
            id=source_id,
            identity_key=identity_key,
            scope=scope,
            owner_user_id=user_id if private else None,
            owner_manuscript_id=manuscript_id if private else None,
            canonical_url=fetched.canonical_url,
            title=fetched.title,
            publisher=fetched.publisher,
            published_at=fetched.published_at,
            fetched_at=fetched.fetched_at,
            content_hash=fetched.content_hash,
            storage_key=f"research_sources/{source_id}.json",
            language=language,
            status=ResearchSourceStatus.PENDING,
            embedding_model=embedding_model,
            embedding_dimension=embedding_dimension,
            chunk_schema_version=chunk_schema_version,
        )


class ResearchSourceUrl(Base):
    __tablename__ = "research_source_urls"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    identity_key: Mapped[str] = mapped_column(String(64), unique=True)
    source_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("research_sources.id"), index=True
    )
    url: Mapped[str] = mapped_column(Text)
    scope: Mapped[ResearchSourceScope] = mapped_column(SAEnum(ResearchSourceScope))
    owner_user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id"), nullable=True
    )
    owner_manuscript_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("manuscripts.id"), nullable=True
    )
    is_canonical: Mapped[bool] = mapped_column(default=False)

    @classmethod
    def for_source(
        cls,
        source: ResearchSource,
        *,
        url: str,
        identity_key: str,
        is_canonical: bool,
    ) -> ResearchSourceUrl:
        return cls(
            identity_key=identity_key,
            source_id=source.id,
            url=url,
            scope=source.scope,
            owner_user_id=source.owner_user_id,
            owner_manuscript_id=source.owner_manuscript_id,
            is_canonical=is_canonical,
        )


class ResearchJobSource(Base):
    __tablename__ = "research_job_sources"
    __table_args__ = (
        UniqueConstraint("research_job_id", "source_id", name="uq_research_job_source"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    research_job_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("research_jobs.id"), index=True
    )
    source_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("research_sources.id"), index=True
    )
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    manuscript_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("manuscripts.id"))

    @classmethod
    def for_job_and_source(
        cls, job: ResearchJob, source: ResearchSource
    ) -> ResearchJobSource:
        return cls(
            research_job_id=job.id,
            source_id=source.id,
            user_id=job.user_id,
            manuscript_id=job.manuscript_id,
        )


class ResearchUsage(Base):
    """원고별 조사 job·웹 검색 사용량. 상한·관측용 카운터만 둔다."""

    __tablename__ = "research_usage"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    manuscript_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("manuscripts.id"), unique=True, index=True
    )
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), index=True)
    job_count: Mapped[int] = mapped_column(Integer, default=0)
    search_count: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime, default=datetime.datetime.utcnow
    )
    updated_at: Mapped[datetime.datetime] = mapped_column(
        DateTime,
        default=datetime.datetime.utcnow,
        onupdate=datetime.datetime.utcnow,
    )


class ResponseComparisonRecord(Base):
    """조사 job 완료 시 baseline/grounded 쌍과 LLM 비교 결과를 저장한다."""

    __tablename__ = "response_comparison_records"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    research_job_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("research_jobs.id"), unique=True, index=True
    )
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), index=True)
    manuscript_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("manuscripts.id"), index=True
    )
    message_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("chat_messages.id"), nullable=True
    )
    baseline_body: Mapped[str] = mapped_column(Text)
    grounded_body: Mapped[str] = mapped_column(Text)
    baseline_cited_urls: Mapped[str] = mapped_column(Text, default="[]")
    grounded_cited_urls: Mapped[str] = mapped_column(Text, default="[]")
    baseline_citation_passed: Mapped[bool] = mapped_column(default=True)
    grounded_citation_passed: Mapped[bool] = mapped_column(default=True)
    citation_failure_reasons: Mapped[str | None] = mapped_column(Text, nullable=True)
    # PairwiseJudgment JSON (점수·winner·reason·order_flipped)
    judgment_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    generation_model: Mapped[str | None] = mapped_column(String(128), nullable=True)
    judge_model: Mapped[str | None] = mapped_column(String(128), nullable=True)
    comparison_error: Mapped[str | None] = mapped_column(String(128), nullable=True)
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime, default=datetime.datetime.utcnow
    )

    @classmethod
    def from_job_evaluation(
        cls,
        job: ResearchJob,
        *,
        baseline: GeneratedResponse,
        grounded: GroundedResponseResult,
        judgment: PairwiseJudgment | None,
        generation_model: str | None,
        judge_model: str | None,
        comparison_error: str | None,
    ) -> ResponseComparisonRecord:
        return cls(
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
                [citation.url for citation in grounded.citations],
                ensure_ascii=False,
            ),
            baseline_citation_passed=True,
            grounded_citation_passed=grounded.is_grounded,
            citation_failure_reasons=grounded.warning_code,
            judgment_json=judgment.model_dump_json() if judgment else None,
            generation_model=generation_model,
            judge_model=judge_model,
            comparison_error=comparison_error,
        )
