from pydantic import BaseModel, Field

from app.models.manuscript import ConceptType, ManuscriptStatus


class ManuscriptCreateRequest(BaseModel):
    topic: str = Field(..., min_length=1, max_length=255)
    concept: ConceptType
    audience_level: str | None = None


class ManuscriptResponse(BaseModel):
    id: str
    topic: str
    concept: ConceptType
    status: ManuscriptStatus
    audience_level: str | None = None
