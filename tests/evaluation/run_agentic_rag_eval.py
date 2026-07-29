import argparse
import json
from collections.abc import Callable, Mapping
from dataclasses import dataclass, fields
from pathlib import Path

EVALUATION_SCHEMA_VERSION = 1


@dataclass(frozen=True)
class EvaluationCase:
    schema_version: int
    case_id: str
    category: str
    language_pair: str
    input: str
    expected_research_required: bool
    expected_source_keys: tuple[str, ...]
    expected_chunk_keys: tuple[str, ...]
    reference_answer: str | None
    must_abstain: bool
    forbidden_source_keys: tuple[str, ...]


@dataclass(frozen=True)
class EvaluationPrediction:
    case_id: str
    research_required: bool = False
    retrieved_source_keys: tuple[str, ...] = ()
    retrieved_chunk_keys: tuple[str, ...] = ()
    citation_source_keys: tuple[str, ...] = ()
    citation_chunk_keys: tuple[str, ...] = ()
    abstained: bool = False


SemanticEvaluator = Callable[
    [EvaluationCase, EvaluationPrediction], Mapping[str, object]
]


def load_evaluation_cases(path: Path) -> list[EvaluationCase]:
    cases = []
    expected_fields = {field.name for field in fields(EvaluationCase)}
    for line_number, line in enumerate(
        path.read_text(encoding="utf-8").splitlines(), start=1
    ):
        if not line.strip():
            continue
        raw = json.loads(line)
        if not isinstance(raw, dict) or set(raw) != expected_fields:
            raise ValueError(f"case schema mismatch on line {line_number}")
        if raw["schema_version"] != EVALUATION_SCHEMA_VERSION:
            raise ValueError(f"unsupported case schema on line {line_number}")
        cases.append(
            EvaluationCase(
                schema_version=raw["schema_version"],
                case_id=raw["case_id"],
                category=raw["category"],
                language_pair=raw["language_pair"],
                input=raw["input"],
                expected_research_required=raw["expected_research_required"],
                expected_source_keys=tuple(raw["expected_source_keys"]),
                expected_chunk_keys=tuple(raw["expected_chunk_keys"]),
                reference_answer=raw["reference_answer"],
                must_abstain=raw["must_abstain"],
                forbidden_source_keys=tuple(raw["forbidden_source_keys"]),
            )
        )
    return cases


def load_predictions(path: Path) -> list[EvaluationPrediction]:
    predictions = []
    expected_fields = {field.name for field in fields(EvaluationPrediction)}
    for line_number, line in enumerate(
        path.read_text(encoding="utf-8").splitlines(), start=1
    ):
        if not line.strip():
            continue
        raw = json.loads(line)
        if not isinstance(raw, dict) or set(raw) != expected_fields:
            raise ValueError(f"prediction schema mismatch on line {line_number}")
        predictions.append(
            EvaluationPrediction(
                case_id=raw["case_id"],
                research_required=raw["research_required"],
                retrieved_source_keys=tuple(raw["retrieved_source_keys"]),
                retrieved_chunk_keys=tuple(raw["retrieved_chunk_keys"]),
                citation_source_keys=tuple(raw["citation_source_keys"]),
                citation_chunk_keys=tuple(raw["citation_chunk_keys"]),
                abstained=raw["abstained"],
            )
        )
    return predictions


def evaluate_run(
    cases: list[EvaluationCase],
    predictions: list[EvaluationPrediction],
    *,
    run_name: str,
    retrieval_k: int,
    semantic_evaluator: SemanticEvaluator | None = None,
) -> dict[str, object]:
    predictions_by_case = {prediction.case_id: prediction for prediction in predictions}
    if len(predictions_by_case) != len(predictions) or set(predictions_by_case) != {
        case.case_id for case in cases
    }:
        raise ValueError("predictions must match evaluation cases")

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

        citation_is_invalid = not set(prediction.citation_source_keys).issubset(
            prediction.retrieved_source_keys
        ) or not set(prediction.citation_chunk_keys).issubset(
            prediction.retrieved_chunk_keys
        )
        if citation_is_invalid:
            failures.append("invalid_citation")
            invalid_citation_case_ids.append(case.case_id)

        exposed_source_keys = set(prediction.retrieved_source_keys).union(
            prediction.citation_source_keys
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
    parser.add_argument("--predictions", type=Path, required=True)
    parser.add_argument("--run-name", required=True)
    parser.add_argument("--retrieval-k", type=int, default=5)
    args = parser.parse_args(argv)
    summary = evaluate_run(
        load_evaluation_cases(args.cases),
        load_predictions(args.predictions),
        run_name=args.run_name,
        retrieval_k=args.retrieval_k,
    )
    print(json.dumps(summary, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
