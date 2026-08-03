from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

Winner = Literal["baseline", "grounded", "tie"]


class FrozenModel(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class PreparedEvidence(FrozenModel):
    source_key: str = Field(min_length=1)
    url: str | None = None
    title: str = Field(min_length=1)
    text: str

    @field_validator("source_key", "title", "text")
    @classmethod
    def strip_required_text(cls, value: str) -> str:
        if not (value := value.strip()):
            raise ValueError("must not be blank")
        return value

    @field_validator("url")
    @classmethod
    def strip_optional_url(cls, value: str | None) -> str | None:
        if value is None:
            return None
        if not (value := value.strip()):
            raise ValueError("url must not be blank")
        return value


class ResponseEvalCase(FrozenModel):
    case_id: str = Field(min_length=1)
    ai_question: str
    human_response: str
    allowed_source_keys: tuple[str, ...] = ()
    forbidden_source_keys: tuple[str, ...] = ()
    prepared_evidence: tuple[PreparedEvidence, ...] = ()

    @field_validator("case_id", "ai_question", "human_response")
    @classmethod
    def strip_required_text(cls, value: str) -> str:
        if not (value := value.strip()):
            raise ValueError("must not be blank")
        return value


class GeneratedResponse(FrozenModel):
    body: str
    cited_source_keys: tuple[str, ...] = ()
    cited_urls: tuple[str, ...] = ()

    @field_validator("body")
    @classmethod
    def strip_body(cls, value: str) -> str:
        if not (value := value.strip()):
            raise ValueError("body must not be blank")
        return value


class SafetyCheckResult(FrozenModel):
    passed: bool
    failure_reasons: tuple[str, ...] = ()


class PairwiseJudgment(FrozenModel):
    specificity_winner: Winner
    naturalness_winner: Winner
    accuracy_winner: Winner
    overall_winner: Winner
    reason: str = Field(min_length=1)
    order_flipped: bool

    @field_validator("reason")
    @classmethod
    def strip_reason(cls, value: str) -> str:
        if not (value := value.strip()):
            raise ValueError("reason must not be blank")
        return value


class CaseEvalResult(FrozenModel):
    case_id: str = Field(min_length=1)
    baseline_response: GeneratedResponse
    grounded_response: GeneratedResponse
    baseline_safety: SafetyCheckResult
    grounded_safety: SafetyCheckResult
    judgment: PairwiseJudgment | None = None


class EvalSummary(FrozenModel):
    case_count: int = Field(ge=0)
    fatal_failure_count: int = Field(ge=0)
    wins: int = Field(ge=0)
    losses: int = Field(ge=0)
    ties: int = Field(ge=0)
    specificity_win_rate: float = Field(ge=0.0, le=1.0)
    naturalness_win_rate: float = Field(ge=0.0, le=1.0)
    accuracy_win_rate: float = Field(ge=0.0, le=1.0)
    order_flip_rate: float = Field(ge=0.0, le=1.0)
    win_rate_threshold: float | None = None
