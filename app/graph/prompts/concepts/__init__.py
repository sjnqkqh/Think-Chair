from pathlib import Path

from app.graph.prompts.md_loader import extract_section
from app.graph.prompts.types import PromptTemplate
from app.models.manuscript import ConceptType

_DIR = Path(__file__).parent


def _load_concept(concept: ConceptType) -> dict[str, PromptTemplate]:
    concept_dir = _DIR / concept.value
    generate_md = (concept_dir / "generate.md").read_text(encoding="utf-8")
    checkpoint_md = (concept_dir / "checkpoint.md").read_text(encoding="utf-8")

    return {
        "generate": PromptTemplate(
            id=f"concept.{concept.value}.generate",
            text=generate_md,
            used_when="outline/draft/polish 생성 단계에서 사용",
            description=f"{concept.value} 문서의 생성 기준 전체 (독자, 구조, 작성 기준, 금지 사항 등).",
        ),
        "checkpoint": PromptTemplate(
            id=f"concept.{concept.value}.checkpoint",
            text=checkpoint_md,
            used_when="inspect/feedback 점검 단계에서 사용",
            description=f"{concept.value} 문서 점검용 체크리스트. GENERATE의 기준을 요약 참조한다.",
        ),
        "purpose": PromptTemplate(
            id=f"concept.{concept.value}.purpose",
            text=extract_section(generate_md, "목적"),
            used_when="say(자유 대화) 단계에서 사용",
            description="generate.md의 '목적' 섹션만 추출한 짧은 맥락 힌트",
        ),
    }


# concept.value(ConceptType) -> {"generate"/"checkpoint"/"purpose": PromptTemplate}
CONCEPT_TEMPLATES = {concept.value: _load_concept(concept) for concept in ConceptType}
