from app.models.manuscript import ConceptType

# 웹 근거 조사는 기술·교육 문서 유형에서만 켠다.
RESEARCH_ENABLED_CONCEPTS = frozenset(
    {
        ConceptType.TECH_DEEPDIVE,
        ConceptType.TEACHING,
    }
)


def concept_allows_web_research(concept: ConceptType) -> bool:
    """원고 컨셉이 Agentic RAG 웹 조사 대상인지 판정한다."""
    return concept in RESEARCH_ENABLED_CONCEPTS
