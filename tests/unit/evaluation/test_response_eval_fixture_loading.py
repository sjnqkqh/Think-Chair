from pathlib import Path

import pytest

from tests.evaluation.agentic_rag_eval_contracts import (
    load_evaluation_cases,
    load_evaluation_corpus,
)
from tests.evaluation.response_eval_bridge import load_response_eval_cases

pytestmark = pytest.mark.unit

CASES_PATH = Path("tests/evaluation/agentic_rag_cases.json")
CORPUS_PATH = Path("tests/evaluation/agentic_rag_corpus.json")


def test_load_response_eval_cases_from_agentic_fixtures_keeps_research_needed_only():
    cases = load_response_eval_cases(
        cases_path=CASES_PATH,
        corpus_path=CORPUS_PATH,
        research_required_only=True,
    )
    source = load_evaluation_cases(CASES_PATH)
    corpus = load_evaluation_corpus(CORPUS_PATH)

    assert cases
    assert len(cases) == sum(1 for item in source if item.expected_research_required)
    assert all(case.ai_question and case.human_response for case in cases)

    with_sources = [case for case in cases if case.allowed_source_keys]
    assert with_sources
    sample = with_sources[0]
    corpus_keys = {chunk.source_key for chunk in corpus}
    assert set(sample.allowed_source_keys).issubset(corpus_keys)
    assert {item.source_key for item in sample.prepared_evidence} == set(
        sample.allowed_source_keys
    )
    assert set(sample.forbidden_source_keys).issubset(corpus_keys)
