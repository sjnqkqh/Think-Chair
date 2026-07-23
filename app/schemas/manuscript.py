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
