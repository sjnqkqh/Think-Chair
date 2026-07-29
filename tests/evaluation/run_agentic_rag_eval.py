import argparse
import json
from collections.abc import Callable, Mapping
from dataclasses import dataclass, fields
from pathlib import Path

EVALUATION_SCHEMA_VERSION = 2


@dataclass(frozen=True)
class EvaluationCase:
    schema_version: int
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


@dataclass(frozen=True)
class EvaluationCorpusChunk:
    schema_version: int
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


@dataclass(frozen=True)
class EvaluationCitation:
    source_key: str
    chunk_key: str
    url: str


@dataclass(frozen=True)
class EvaluationPrediction:
    case_id: str
    research_required: bool = False
    retrieved_source_keys: tuple[str, ...] = ()
    retrieved_chunk_keys: tuple[str, ...] = ()
    citations: tuple[EvaluationCitation, ...] = ()
    abstained: bool = False


SemanticEvaluator = Callable[
    [EvaluationCase, EvaluationPrediction], Mapping[str, object]
]


def load_evaluation_cases(path: Path) -> list[EvaluationCase]:
    cases = []
    expected_fields = _field_names(EvaluationCase)
    for line_number, raw in _load_jsonl(path):
        _require_schema(raw, expected_fields, line_number, "case")
        cases.append(
            EvaluationCase(
                schema_version=raw["schema_version"],
                case_id=raw["case_id"],
                category=raw["category"],
                language_pair=raw["language_pair"],
                ai_question=raw["ai_question"],
                human_response=raw["human_response"],
                expected_research_required=raw["expected_research_required"],
                expected_source_keys=tuple(raw["expected_source_keys"]),
                expected_chunk_keys=tuple(raw["expected_chunk_keys"]),
                reference_answer=raw["reference_answer"],
                must_abstain=raw["must_abstain"],
                forbidden_source_keys=tuple(raw["forbidden_source_keys"]),
            )
        )
    return cases


def load_evaluation_corpus(path: Path) -> list[EvaluationCorpusChunk]:
    corpus = []
    expected_fields = _field_names(EvaluationCorpusChunk)
    for line_number, raw in _load_jsonl(path):
        _require_schema(raw, expected_fields, line_number, "corpus")
        corpus.append(
            EvaluationCorpusChunk(
                schema_version=raw["schema_version"],
                source_key=raw["source_key"],
                chunk_key=raw["chunk_key"],
                url=raw["url"],
                title=raw["title"],
                language=raw["language"],
                text=raw["text"],
                published_at=raw["published_at"],
                fetched_at=raw["fetched_at"],
                scope=raw["scope"],
                owner_user_id=raw["owner_user_id"],
                owner_manuscript_id=raw["owner_manuscript_id"],
            )
        )
    return corpus


def load_predictions(path: Path) -> list[EvaluationPrediction]:
    predictions = []
    expected_fields = _field_names(EvaluationPrediction)
    citation_fields = _field_names(EvaluationCitation)
    for line_number, raw in _load_jsonl(path):
        if not isinstance(raw, dict) or set(raw) != expected_fields:
            raise ValueError(f"prediction schema mismatch on line {line_number}")
        citations = []
        for citation in raw["citations"]:
            if not isinstance(citation, dict) or set(citation) != citation_fields:
                raise ValueError(
                    f"prediction citation schema mismatch on line {line_number}"
                )
            citations.append(EvaluationCitation(**citation))
        predictions.append(
            EvaluationPrediction(
                case_id=raw["case_id"],
                research_required=raw["research_required"],
                retrieved_source_keys=tuple(raw["retrieved_source_keys"]),
                retrieved_chunk_keys=tuple(raw["retrieved_chunk_keys"]),
                citations=tuple(citations),
                abstained=raw["abstained"],
            )
        )
    return predictions


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
    semantic_evaluator: SemanticEvaluator | None = None,
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
                "semantic": (
                    dict(semantic_evaluator(case, prediction))
                    if semantic_evaluator
                    else None
                ),
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


def _field_names(data_class: type) -> set[str]:
    return {field.name for field in fields(data_class)}


def _load_jsonl(path: Path) -> list[tuple[int, object]]:
    text = path.read_text(encoding="utf-8")
    decoder = json.JSONDecoder()
    loaded = []
    position = 0
    while position < len(text):
        while position < len(text) and text[position].isspace():
            position += 1
        if position == len(text):
            break
        line_number = text.count("\n", 0, position) + 1
        raw, position = decoder.raw_decode(text, position)
        loaded.append((line_number, raw))
    return loaded


def _require_schema(
    raw: object,
    expected_fields: set[str],
    line_number: int,
    fixture_name: str,
) -> None:
    if not isinstance(raw, dict) or set(raw) != expected_fields:
        raise ValueError(f"{fixture_name} schema mismatch on line {line_number}")
    if raw["schema_version"] != EVALUATION_SCHEMA_VERSION:
        raise ValueError(f"unsupported {fixture_name} schema on line {line_number}")


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
