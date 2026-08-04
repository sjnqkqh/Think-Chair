from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

ServiceGrowthPhase = Literal["say", "feedback"]


class FrozenModel(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class ServiceGrowthCase(FrozenModel):
    case_id: str = Field(min_length=1)
    phase: ServiceGrowthPhase
    language: str = Field(min_length=1)
    claim: str = Field(min_length=1)
    concept: str = Field(min_length=1)
    topic: str = Field(min_length=1)

    @field_validator("case_id", "language", "claim", "concept", "topic")
    @classmethod
    def strip_required_text(cls, value: str) -> str:
        if not (value := value.strip()):
            raise ValueError("must not be blank")
        return value


class AbsoluteAnswerScores(FrozenModel):
    """지식 심화·근거 제안 품질. '정답 제공'이 목표가 아님."""

    reference_suggestion: int = Field(ge=0, le=100)
    claim_sharpening: int = Field(ge=0, le=100)
    knowledge_depth: int = Field(ge=0, le=100)
    dialogue_fit: int = Field(ge=0, le=100)
    next_step_clarity: int = Field(ge=0, le=100)
    overall: int = Field(ge=0, le=100)


class AbsoluteJudgment(FrozenModel):
    scores: AbsoluteAnswerScores
    reason: str = Field(min_length=1)

    @field_validator("reason")
    @classmethod
    def strip_reason(cls, value: str) -> str:
        if not (value := value.strip()):
            raise ValueError("reason must not be blank")
        return value


class ServiceGrowthCaseResult(FrozenModel):
    case_id: str = Field(min_length=1)
    phase: ServiceGrowthPhase
    claim: str = Field(min_length=1)
    topic: str = Field(min_length=1)
    response_body: str = ""
    evidence_text: str = ""
    judgment: AbsoluteJudgment | None = None
    error: str | None = None


class ServiceGrowthRunSummary(FrozenModel):
    case_count: int = Field(ge=0)
    judged_count: int = Field(ge=0)
    failure_count: int = Field(ge=0)
    avg_reference_suggestion: float | None = None
    avg_claim_sharpening: float | None = None
    avg_knowledge_depth: float | None = None
    avg_dialogue_fit: float | None = None
    avg_next_step_clarity: float | None = None
    avg_overall: float | None = None
    generation_model: str | None = None
    judge_model: str | None = None
