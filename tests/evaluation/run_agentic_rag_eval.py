import argparse
import json
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


class EvaluationCitation(FrozenEvaluationModel):
    source_key: str
    chunk_key: str
    url: str


class EvaluationPrediction(FrozenEvaluationModel):
    case_id: str
    research_required: bool = False
    retrieved_source_keys: tuple[str, ...] = ()
    retrieved_chunk_keys: tuple[str, ...] = ()
    citations: tuple[EvaluationCitation, ...] = ()
    abstained: bool = False

def load_evaluation_cases(path: Path) -> list[EvaluationCase]:
    return TypeAdapter(list[EvaluationCase]).validate_json(
        path.read_text(encoding="utf-8")
    )


def load_evaluation_corpus(path: Path) -> list[EvaluationCorpusChunk]:
    return TypeAdapter(list[EvaluationCorpusChunk]).validate_json(
        path.read_text(encoding="utf-8")
    )


def load_predictions(path: Path) -> list[EvaluationPrediction]:
    return TypeAdapter(list[EvaluationPrediction]).validate_json(
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


def evaluate_run(
    cases: list[EvaluationCase],
    predictions: list[EvaluationPrediction],
    *,
    corpus: list[EvaluationCorpusChunk],
    run_name: str,
    retrieval_k: int,
) -> dict[str, object]:
    validate_evaluation_fixture(cases, corpus)
    predictions_by_case = {prediction.case_id: prediction for prediction in predictions}
    if len(predictions_by_case) != len(predictions) or set(predictions_by_case) != {
        case.case_id for case in cases
    }:
        raise ValueError("predictions must match evaluation cases")

    chunks_by_key = {chunk.chunk_key: chunk for chunk in corpus}
    true_positive = false_positive = false_negative = true_negative = 0
    source_recalls = []
    chunk_recalls = []
    case_results = []
    invalid_citation_case_ids = []
    tenant_leak_case_ids = []
    missed_abstention_case_ids = []
    for case in cases:
        prediction = predictions_by_case[case.case_id]
        expected = case.expected_research_required
        actual = prediction.research_required
        failures = []
        if expected and actual:
            true_positive += 1
        elif not expected and actual:
            false_positive += 1
        elif expected:
            false_negative += 1
        else:
            true_negative += 1
        if expected != actual:
            failures.append("detector_mismatch")

        if case.expected_source_keys:
            source_recall = _recall_at_k(
                case.expected_source_keys,
                prediction.retrieved_source_keys,
                retrieval_k,
            )
            chunk_recall = _recall_at_k(
                case.expected_chunk_keys,
                prediction.retrieved_chunk_keys,
                retrieval_k,
            )
            source_recalls.append(source_recall)
            chunk_recalls.append(chunk_recall)
            if source_recall < 1:
                failures.append("missing_expected_source")
            if chunk_recall < 1:
                failures.append("missing_expected_chunk")

        if not _citations_are_valid(prediction, chunks_by_key):
            failures.append("invalid_citation")
            invalid_citation_case_ids.append(case.case_id)

        exposed_source_keys = set(prediction.retrieved_source_keys).union(
            citation.source_key for citation in prediction.citations
        )
        if set(case.forbidden_source_keys).intersection(exposed_source_keys):
            failures.append("tenant_leak")
            tenant_leak_case_ids.append(case.case_id)

        if case.must_abstain and not prediction.abstained:
            failures.append("missed_abstention")
            missed_abstention_case_ids.append(case.case_id)

        case_results.append(
            {
                "case_id": case.case_id,
                "passed": not failures,
                "failures": failures,
            }
        )

    return {
        "schema_version": EVALUATION_SCHEMA_VERSION,
        "run_name": run_name,
        "case_count": len(cases),
        "detector": {
            "true_positive": true_positive,
            "false_positive": false_positive,
            "false_negative": false_negative,
            "true_negative": true_negative,
            "precision": _ratio(true_positive, true_positive + false_positive),
            "recall": _ratio(true_positive, true_positive + false_negative),
        },
        "retrieval": {
            "k": retrieval_k,
            "evaluated_cases": len(source_recalls),
            "source_recall_at_k": _average(source_recalls),
            "chunk_recall_at_k": _average(chunk_recalls),
        },
        "safety": {
            "invalid_citation_case_ids": invalid_citation_case_ids,
            "tenant_leak_case_ids": tenant_leak_case_ids,
            "missed_abstention_case_ids": missed_abstention_case_ids,
        },
        "passed": all(result["passed"] for result in case_results),
        "cases": case_results,
    }


def _citations_are_valid(
    prediction: EvaluationPrediction,
    chunks_by_key: dict[str, EvaluationCorpusChunk],
) -> bool:
    retrieved_source_keys = set(prediction.retrieved_source_keys)
    retrieved_chunk_keys = set(prediction.retrieved_chunk_keys)
    for citation in prediction.citations:
        chunk = chunks_by_key.get(citation.chunk_key)
        if (
            citation.source_key not in retrieved_source_keys
            or citation.chunk_key not in retrieved_chunk_keys
            or chunk is None
            or chunk.source_key != citation.source_key
            or chunk.url != citation.url
        ):
            return False
    return True


def _recall_at_k(expected: tuple[str, ...], actual: tuple[str, ...], k: int) -> float:
    expected_keys = set(expected)
    if not expected_keys:
        return 1.0
    return len(expected_keys.intersection(actual[:k])) / len(expected_keys)


def _ratio(numerator: int, denominator: int) -> float:
    return numerator / denominator if denominator else 0.0


def _average(values: list[float]) -> float:
    return sum(values) / len(values) if values else 0.0


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--cases", type=Path, required=True)
    parser.add_argument("--corpus", type=Path, required=True)
    parser.add_argument("--predictions", type=Path, required=True)
    parser.add_argument("--run-name", required=True)
    parser.add_argument("--retrieval-k", type=int, default=5)
    args = parser.parse_args(argv)
    summary = evaluate_run(
        load_evaluation_cases(args.cases),
        load_predictions(args.predictions),
        corpus=load_evaluation_corpus(args.corpus),
        run_name=args.run_name,
        retrieval_k=args.retrieval_k,
    )
    print(json.dumps(summary, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
