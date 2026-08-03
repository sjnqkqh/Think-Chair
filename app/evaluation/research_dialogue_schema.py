from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, TypeAdapter

EVALUATION_SCHEMA_VERSION = 2


class FrozenEvaluationModel(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class EvaluationCase(FrozenEvaluationModel):
    schema_version: Literal[2]
    case_id: str
    category: str
    language_pair: str
    ai_question: str
    human_response: str
    expected_research_required: bool
    expected_source_keys: tuple[str, ...]
    expected_chunk_keys: tuple[str, ...]
    reference_answer: str | None
    must_abstain: bool
    forbidden_source_keys: tuple[str, ...]


class EvaluationCorpusChunk(FrozenEvaluationModel):
    schema_version: Literal[2]
    source_key: str
    chunk_key: str
    url: str
    title: str
    language: str
    text: str
    published_at: str | None
    fetched_at: str
    scope: str
    owner_user_id: str | None
    owner_manuscript_id: str | None


def load_evaluation_cases(path: Path) -> list[EvaluationCase]:
    return TypeAdapter(list[EvaluationCase]).validate_json(
        path.read_text(encoding="utf-8")
    )


def load_evaluation_corpus(path: Path) -> list[EvaluationCorpusChunk]:
    return TypeAdapter(list[EvaluationCorpusChunk]).validate_json(
        path.read_text(encoding="utf-8")
    )


def validate_evaluation_fixture(
    cases: list[EvaluationCase],
    corpus: list[EvaluationCorpusChunk],
) -> None:
    chunks_by_key = {chunk.chunk_key: chunk for chunk in corpus}
    if len(chunks_by_key) != len(corpus):
        raise ValueError("corpus chunk keys must be unique")

    source_keys = {chunk.source_key for chunk in corpus}
    expected_source_keys = {
        source_key
        for case in cases
        for source_key in (*case.expected_source_keys, *case.forbidden_source_keys)
    }
    expected_chunk_keys = {
        chunk_key for case in cases for chunk_key in case.expected_chunk_keys
    }
    if not expected_source_keys.issubset(source_keys):
        raise ValueError("evaluation case references an unknown source")
    if not expected_chunk_keys.issubset(chunks_by_key):
        raise ValueError("evaluation case references an unknown chunk")
