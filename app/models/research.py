from __future__ import annotations

import datetime
import enum
import uuid

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy import Enum as SAEnum
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


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
