import json
from dataclasses import FrozenInstanceError, replace
from pathlib import Path

import pytest

from tests.evaluation.run_agentic_rag_eval import (
    EVALUATION_SCHEMA_VERSION,
    EvaluationPrediction,
    evaluate_run,
    load_evaluation_cases,
    main,
)

pytestmark = pytest.mark.unit

CASES_PATH = Path("tests/evaluation/agentic_rag_cases.jsonl")


def test_load_evaluation_cases_freezes_the_multilingual_fixture():
    cases = load_evaluation_cases(CASES_PATH)

    assert cases
    assert {case.language_pair for case in cases} == {
        "ko-ko",
        "en-en",
        "ko-en",
        "en-ko",
        "mixed",
    }
    assert all(case.schema_version == EVALUATION_SCHEMA_VERSION for case in cases)
    assert any(case.expected_source_keys for case in cases)
    assert any(case.expected_chunk_keys for case in cases)
    assert any(case.forbidden_source_keys for case in cases)
    with pytest.raises(FrozenInstanceError):
        cases[0].case_id = "changed"


@pytest.mark.parametrize(
    "mutation",
    [
        lambda case: case.update(schema_version=2),
        lambda case: case.update(unexpected_field=True),
    ],
)
def test_load_evaluation_cases_rejects_schema_changes(tmp_path, mutation):
    raw_case = json.loads(CASES_PATH.read_text(encoding="utf-8").splitlines()[0])
    mutation(raw_case)
    path = tmp_path / "changed-schema.jsonl"
    path.write_text(json.dumps(raw_case), encoding="utf-8")

    with pytest.raises(ValueError, match="schema"):
        load_evaluation_cases(path)


def test_evaluate_run_measures_detector_and_retrieval_results():
    loaded_cases = load_evaluation_cases(CASES_PATH)
    positive_case = next(
        case for case in loaded_cases if case.case_id == "embedding-benchmark-ko-en"
    )
    missed_positive_case = next(
        case for case in loaded_cases if case.case_id == "python-docs-en"
    )
    negative_case = next(case for case in loaded_cases if case.case_id == "casual-ko")
    true_negative_case = replace(negative_case, case_id="casual-en")
    cases = [
        positive_case,
        missed_positive_case,
        negative_case,
        true_negative_case,
    ]
    predictions = [
        EvaluationPrediction(
            case_id=positive_case.case_id,
            research_required=True,
            retrieved_source_keys=positive_case.expected_source_keys,
            retrieved_chunk_keys=positive_case.expected_chunk_keys,
            citation_source_keys=positive_case.expected_source_keys,
            citation_chunk_keys=positive_case.expected_chunk_keys,
            abstained=False,
        ),
        EvaluationPrediction(case_id=missed_positive_case.case_id),
        EvaluationPrediction(
            case_id=negative_case.case_id,
            research_required=True,
        ),
        EvaluationPrediction(case_id=true_negative_case.case_id),
    ]

    summary = evaluate_run(cases, predictions, run_name="candidate", retrieval_k=5)

    assert summary["detector"] == {
        "true_positive": 1,
        "false_positive": 1,
        "false_negative": 1,
        "true_negative": 1,
        "precision": 0.5,
        "recall": 0.5,
    }
    assert summary["retrieval"] == {
        "k": 5,
        "evaluated_cases": 2,
        "source_recall_at_k": 0.5,
        "chunk_recall_at_k": 0.5,
    }


def test_evaluate_run_fails_invalid_citations_tenant_leaks_and_missed_abstention():
    tenant_case = next(
        case
        for case in load_evaluation_cases(CASES_PATH)
        if case.case_id == "tenant-isolation"
    )
    case = replace(tenant_case, must_abstain=True)
    prediction = EvaluationPrediction(
        case_id=case.case_id,
        research_required=True,
        retrieved_source_keys=(
            *case.expected_source_keys,
            *case.forbidden_source_keys,
        ),
        retrieved_chunk_keys=case.expected_chunk_keys,
        citation_source_keys=("invented-source",),
        citation_chunk_keys=("invented-source#claim",),
        abstained=False,
    )

    summary = evaluate_run([case], [prediction], run_name="candidate", retrieval_k=5)

    assert summary["passed"] is False
    assert summary["safety"] == {
        "invalid_citation_case_ids": [case.case_id],
        "tenant_leak_case_ids": [case.case_id],
        "missed_abstention_case_ids": [case.case_id],
    }
    assert summary["cases"][0]["failures"] == [
        "invalid_citation",
        "tenant_leak",
        "missed_abstention",
    ]


def test_cli_outputs_comparable_machine_readable_summaries(tmp_path, capsys):
    cases = load_evaluation_cases(CASES_PATH)
    prediction_path = tmp_path / "predictions.jsonl"
    prediction_path.write_text(
        "\n".join(
            json.dumps(
                {
                    "case_id": case.case_id,
                    "research_required": case.expected_research_required,
                    "retrieved_source_keys": case.expected_source_keys,
                    "retrieved_chunk_keys": case.expected_chunk_keys,
                    "citation_source_keys": [],
                    "citation_chunk_keys": [],
                    "abstained": case.must_abstain,
                }
            )
            for case in cases
        ),
        encoding="utf-8",
    )

    outputs = []
    for run_name in ("baseline", "candidate"):
        main(
            [
                "--cases",
                str(CASES_PATH),
                "--predictions",
                str(prediction_path),
                "--run-name",
                run_name,
            ]
        )
        outputs.append(json.loads(capsys.readouterr().out))

    baseline, candidate = outputs
    assert baseline["run_name"] == "baseline"
    assert candidate["run_name"] == "candidate"
    assert baseline["passed"] is True
    assert baseline.keys() == candidate.keys()
    assert baseline["detector"].keys() == candidate["detector"].keys()
    assert baseline["retrieval"].keys() == candidate["retrieval"].keys()
    assert baseline["safety"].keys() == candidate["safety"].keys()


def test_evaluate_run_keeps_semantic_evaluation_optional():
    case = next(
        case
        for case in load_evaluation_cases(CASES_PATH)
        if case.case_id == "casual-ko"
    )
    prediction = EvaluationPrediction(case_id=case.case_id)

    summary = evaluate_run(
        [case],
        [prediction],
        run_name="candidate",
        retrieval_k=5,
        semantic_evaluator=lambda evaluated_case, _: {
            "case_id": evaluated_case.case_id,
            "score": 0.8,
        },
    )

    assert summary["cases"][0]["semantic"] == {
        "case_id": case.case_id,
        "score": 0.8,
    }
