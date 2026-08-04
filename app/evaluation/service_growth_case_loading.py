import json
from pathlib import Path

from app.evaluation.service_growth_contracts import ServiceGrowthCase


def load_service_growth_cases(cases_path: Path) -> list[ServiceGrowthCase]:
    raw = json.loads(cases_path.read_text(encoding="utf-8"))
    if not isinstance(raw, list):
        raise ValueError("service growth cases must be a JSON array")
    return [ServiceGrowthCase.model_validate(item) for item in raw]


def assert_service_growth_corpus_shape(cases: list[ServiceGrowthCase]) -> None:
    """고정 문제집 계약: 50건, say:feedback=40:10, 기타 도메인 ≤2."""
    if len(cases) != 50:
        raise ValueError(f"expected 50 cases, got {len(cases)}")
    say = sum(1 for case in cases if case.phase == "say")
    feedback = sum(1 for case in cases if case.phase == "feedback")
    if say != 40 or feedback != 10:
        raise ValueError(f"expected say:feedback 40:10, got {say}:{feedback}")
    primary = {"ai", "fastapi", "python"}
    other = [case for case in cases if case.domain not in primary]
    if len(other) > 2:
        raise ValueError(f"expected at most 2 non-primary domains, got {len(other)}")
    ids = [case.case_id for case in cases]
    if len(ids) != len(set(ids)):
        raise ValueError("duplicate case_id in service growth cases")
