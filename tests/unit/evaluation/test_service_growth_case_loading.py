from pathlib import Path

import pytest

from app.core.config import PROJECT_ROOT
from app.evaluation.service_growth_case_loading import (
    assert_service_growth_corpus_shape,
    load_service_growth_cases,
)

pytestmark = pytest.mark.unit

CASES_PATH = PROJECT_ROOT / "tests/evaluation/service_growth_cases.json"


def test_service_growth_corpus_matches_fixed_shape():
    cases = load_service_growth_cases(CASES_PATH)
    assert_service_growth_corpus_shape(cases)
    assert len(cases) == 50
    assert sum(1 for case in cases if case.phase == "say") == 40
    assert sum(1 for case in cases if case.phase == "feedback") == 10


def test_assert_shape_rejects_wrong_count(tmp_path: Path):
    cases = load_service_growth_cases(CASES_PATH)[:10]
    with pytest.raises(ValueError, match="50"):
        assert_service_growth_corpus_shape(cases)
