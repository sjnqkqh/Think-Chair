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


class SourceChunk(BaseModel):
    id: str
    source_id: UUID
    ordinal: int
    text: str
    start_index: int
    source_url: str
    section_kind: Literal["page", "comment", "reply"]
    language: Literal["ko", "en", "mixed", "und"]
    chunk_schema_version: str


class IndexRequest(BaseModel):
    research_job_id: UUID
    user_id: UUID
    manuscript_id: UUID
    sources: list[FetchedSource]


class IndexResult(BaseModel):
    indexed_source_ids: list[UUID] = Field(default_factory=list)
    chunk_count: int = 0
    skipped_source_keys: list[str] = Field(default_factory=list)
    error_codes: list[str] = Field(default_factory=list)
    status: Literal["completed", "partial", "failed"]
