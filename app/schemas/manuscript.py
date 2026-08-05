import datetime

from pydantic import BaseModel, Field, model_validator

from app.models.manuscript import ConceptType, ManuscriptStatus


class ManuscriptCreateRequest(BaseModel):
    topic: str = Field(..., min_length=1, max_length=255)
    concept: ConceptType
    audience_level: str | None = Field(default=None, max_length=64)

    @model_validator(mode="after")
    def validate_audience_level(self):
        audience_level = (self.audience_level or "").strip()
        if self.concept == ConceptType.TEACHING and not audience_level:
            raise ValueError("수업 자료에는 독자 수준이 필요합니다.")
        self.audience_level = audience_level
        return self


class ManuscriptResponse(BaseModel):
    id: str
    topic: str
    concept: ConceptType
    status: ManuscriptStatus
    audience_level: str | None = None


class DocumentEvaluationResponse(BaseModel):
    id: str
    version_id: str
    score: int | None = None
    verdict: str | None = None
    reason: str | None = None
    improvements: str | None = None
    has_unnecessary_header: bool | None = None
    has_unnecessary_footer: bool | None = None
    checklist_id: str | None = None
    raw_output: str | None = None
    created_at: datetime.datetime
