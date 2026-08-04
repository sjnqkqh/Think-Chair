from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.evaluation.response_comparison_contracts import AnswerScores

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


class AbsoluteJudgment(FrozenModel):
    scores: AnswerScores
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
    avg_specificity: float | None = None
    avg_naturalness: float | None = None
    avg_accuracy: float | None = None
    avg_overall: float | None = None
    generation_model: str | None = None
    judge_model: str | None = None
