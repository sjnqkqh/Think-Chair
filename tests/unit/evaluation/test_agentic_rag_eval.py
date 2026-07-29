import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from tests.evaluation.agentic_rag_eval_contracts import (
    EVALUATION_SCHEMA_VERSION,
    load_evaluation_cases,
    load_evaluation_corpus,
    validate_evaluation_fixture,
)

pytestmark = pytest.mark.unit

CASES_PATH = Path("tests/evaluation/agentic_rag_cases.json")
CORPUS_PATH = Path("tests/evaluation/agentic_rag_corpus.json")


def test_evaluation_cases_define_product_aligned_multilingual_dialogues():
    """후속 기능이 같은 제품 대화와 다국어 조건으로 평가되도록 사례 계약을 고정한다."""
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
    assert all(case.ai_question.strip() and case.human_response.strip() for case in cases)
    assert sum(case.expected_research_required for case in cases) >= 3
    assert sum(not case.expected_research_required for case in cases) >= 3
    assert {
        case.language_pair for case in cases if case.expected_source_keys
    } == {"ko-ko", "en-en", "ko-en", "en-ko", "mixed"}
    assert any(case.expected_source_keys for case in cases)
    assert any(case.forbidden_source_keys for case in cases)
    with pytest.raises(ValidationError, match="frozen"):
        cases[0].case_id = "changed"


def test_evaluation_corpus_covers_expected_sources_chunks_and_urls():
    """후속 검색 평가가 사용할 모든 기대 근거와 원본 URL이 corpus에 존재하는지 검증한다."""
    cases = load_evaluation_cases(CASES_PATH)
    corpus = load_evaluation_corpus(CORPUS_PATH)

    validate_evaluation_fixture(cases, corpus)

    assert corpus
    assert len({chunk.chunk_key for chunk in corpus}) == len(corpus)
    assert all(chunk.url.startswith("https://") for chunk in corpus)
    assert {"ko", "en"}.issubset({chunk.language for chunk in corpus})


@pytest.mark.parametrize(
    "mutation",
    [
        lambda case: case.update(schema_version=EVALUATION_SCHEMA_VERSION + 1),
        lambda case: case.update(unexpected_field=True),
        lambda case: (
            case.__setitem__("input", case.pop("human_response")),
            case.pop("ai_question"),
        ),
    ],
)
def test_evaluation_cases_reject_unplanned_schema_changes(tmp_path, mutation):
    """후속 PR이 합의된 평가 입력 구조를 암묵적으로 바꾸지 못하도록 잘못된 schema를 거부한다."""
    raw_case = load_evaluation_cases(CASES_PATH)[0].model_dump(mode="json")
    mutation(raw_case)
    path = tmp_path / "changed-schema.json"
    path.write_text(json.dumps([raw_case]), encoding="utf-8")

    with pytest.raises(ValidationError):
        load_evaluation_cases(path)


@pytest.mark.xfail(
    strict=True,
    reason="PR 03 must replace this gap with implementation-backed retrieval evaluation",
)
def test_pr03_must_evaluate_retrieval_citations_and_tenant_isolation():
    """PR 03 전에는 실제 검색 결과가 없으므로 검색·인용·격리 평가는 의도적으로 실패한다."""
    pytest.fail("retrieval and grounded response are not implemented")


@pytest.mark.xfail(
    strict=True,
    reason="PR 04 must replace this gap with implementation-backed detector evaluation",
)
def test_pr04_must_evaluate_research_requirement_detection():
    """PR 04 전에는 실제 판별 결과가 없으므로 조사 필요 여부 평가는 의도적으로 실패한다."""
    pytest.fail("evidence need detector is not implemented")
