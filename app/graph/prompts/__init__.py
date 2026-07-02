from app.graph.prompts.concepts import CONCEPT_TEMPLATES
from app.graph.prompts.constraints.ascii_ban import ASCII_DIAGRAM_BAN
from app.graph.prompts.constraints.emoji_ban import EMOJI_BAN
from app.graph.prompts.constraints.hanja_ban import HANJA_BAN
from app.graph.prompts.persona.base_persona import BASE_PERSONA
from app.graph.prompts.phases.draft import DRAFT
from app.graph.prompts.phases.feedback import FEEDBACK
from app.graph.prompts.phases.inspect import INSPECT
from app.graph.prompts.phases.outline import OUTLINE
from app.graph.prompts.phases.polish import POLISH
from app.graph.prompts.phases.say import SAY
from app.graph.prompts.types import PromptTemplate

# user_action -> 해당 phase가 사용할 concept 콘텐츠의 역할(role)
PHASE_ROLES = {
    "say": "purpose",
    "inspect": "checkpoint",
    "feedback": "checkpoint",
    "outline": "generate",
    "draft": "generate",
    "polish": "generate",
}

# user_action -> phase 지시문 템플릿. 그래프 라우터의 route_by_action과 1:1 대응.
PHASE_INSTRUCTIONS = {
    "say": SAY,
    "inspect": INSPECT,
    "feedback": FEEDBACK,
    "outline": OUTLINE,
    "draft": DRAFT,
    "polish": POLISH,
}

# concept/phase와 무관하게 모든 시스템 프롬프트에 항상 포함되는 전역 제약.
GLOBAL_CONSTRAINTS = [HANJA_BAN, ASCII_DIAGRAM_BAN, EMOJI_BAN]


def get_concept_content(concept: str, phase: str) -> PromptTemplate:
    concept_key = concept.value if hasattr(concept, "value") else concept
    role = PHASE_ROLES[phase]
    return CONCEPT_TEMPLATES[concept_key][role]


def build_system_prompt(
    concept: str, phase: str, *, topic: str, audience: str | None = None
) -> str:
    concept_content = get_concept_content(concept, phase)
    phase_template = PHASE_INSTRUCTIONS[phase]

    context = f"[주제] {topic}"
    if audience:
        context += f"\n[독자 수준] {audience}"

    parts = [
        BASE_PERSONA.text,
        *(constraint.text for constraint in GLOBAL_CONSTRAINTS),
        concept_content.text,
        phase_template.text,
        context,
    ]
    return "\n\n".join(parts)
