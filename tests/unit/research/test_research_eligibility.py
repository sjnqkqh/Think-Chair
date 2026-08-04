import pytest

from app.models.manuscript import ConceptType
from app.research.research_eligibility import (
    RESEARCH_ENABLED_CONCEPTS,
    concept_allows_web_research,
)

pytestmark = pytest.mark.unit


@pytest.mark.parametrize(
    "concept",
    [ConceptType.TECH_DEEPDIVE, ConceptType.TEACHING],
)
def test_deepdive_and_teaching_allow_web_research(concept):
    assert concept_allows_web_research(concept) is True


@pytest.mark.parametrize(
    "concept",
    [ConceptType.RETROSPECTIVE, ConceptType.ESSAY, ConceptType.TIL],
)
def test_other_concepts_disable_web_research(concept):
    assert concept_allows_web_research(concept) is False


def test_research_enabled_concepts_are_exactly_deepdive_and_teaching():
    assert RESEARCH_ENABLED_CONCEPTS == frozenset(
        {ConceptType.TECH_DEEPDIVE, ConceptType.TEACHING}
    )
