from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field, field_validator


class SearchRequest(BaseModel):
    query: str = Field(min_length=1, max_length=400)
    max_results: int = Field(default=5, ge=1, le=20)
    allowed_domains: list[str] | None = None

    @field_validator("query")
    @classmethod
    def strip_query(cls, value: str) -> str:
        if not (value := value.strip()):
            raise ValueError("query must not be blank")
        if len(value.split()) > 50:
            raise ValueError("query must contain at most 50 words")
        return value


class SearchHit(BaseModel):
    url: str
    title: str
    snippet: str
    publisher: str | None = None
    published_at: str | None = None
    provider_rank: int


class SearchResponse(BaseModel):
    results: list[SearchHit] = Field(default_factory=list)
    error_code: str | None = None
    retryable: bool = False


class FetchRequest(BaseModel):
    url: str


class ExtractedSection(BaseModel):
    kind: Literal["comment", "reply"]
    text: str
    permalink: str
    parent_permalink: str | None = None


class ParsedPage(BaseModel):
    canonical_url: str
    title: str
    publisher: str | None = None
    published_at: str | None = None
    text: str
    sections: list[ExtractedSection] = Field(default_factory=list)


class FetchedSource(ParsedPage):
    requested_url: str
    media_type: str
    fetched_at: datetime
    content_hash: str
    source_key: str


class FetchResponse(BaseModel):
    source: FetchedSource | None = None
    error_code: str | None = None
    retryable: bool = False


class ResearchSourceChunk(BaseModel):
    id: str
    source_id: UUID
    ordinal: int
    text: str
    start_index: int
    source_url: str
    section_kind: Literal["page", "comment", "reply"]
    language: Literal["ko", "en", "mixed", "und"]
    chunk_schema_version: str


class ResearchIndexRequest(BaseModel):
    research_job_id: UUID
    user_id: UUID
    manuscript_id: UUID
    sources: list[FetchedSource]


class ResearchIndexResult(BaseModel):
    indexed_source_ids: list[UUID] = Field(default_factory=list)
    chunk_count: int = 0
    skipped_source_keys: list[str] = Field(default_factory=list)
    error_codes: list[str] = Field(default_factory=list)
    status: Literal["completed", "partial", "failed"]


class EvidenceRequest(BaseModel):
    user_id: UUID
    manuscript_id: UUID
    query: str = Field(min_length=1)
    limit: int = Field(default=5, ge=1, le=20)

    @field_validator("query")
    @classmethod
    def strip_query_text(cls, value: str) -> str:
        if not (value := value.strip()):
            raise ValueError("query must not be blank")
        return value


class EvidenceSufficiency(BaseModel):
    sufficient: bool
    missing_aspects: list[str] = Field(default_factory=list)
    supporting_chunk_ids: list[str] = Field(default_factory=list)
    reason_code: str


class EvidenceItem(BaseModel):
    chunk_id: str
    source_id: str
    excerpt: str
    score: float
    title: str = ""
    url: str = ""
    language: str = "und"
    published_at: str | None = None
    fetched_at: str | None = None
    source_type: str | None = None
    claim_relevance: str | None = None
    freshness: str | None = None
    is_primary_source: bool | None = None
    independence_group: str | None = None
    expected_treatment: str | None = None


class EvidenceContext(BaseModel):
    items: list[EvidenceItem] = Field(default_factory=list)
    sufficiency: EvidenceSufficiency
    is_grounded: bool
    warning_code: str | None = None


class Citation(BaseModel):
    source_id: str
    chunk_id: str
    url: str


class GroundedResponseRequest(BaseModel):
    phase: Literal["say", "feedback"]
    conversation_context: str
    evidence: EvidenceContext


class GroundedResponseResult(BaseModel):
    text: str
    citations: list[Citation] = Field(default_factory=list)
    is_grounded: bool
    warning_code: str | None = None
