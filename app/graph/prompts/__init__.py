from app.graph.prompts.concepts import CONCEPT_TEMPLATES
from app.graph.prompts.constraints.ascii_ban import ASCII_DIAGRAM_BAN
from app.graph.prompts.constraints.chinese_ban import CHINESE_BAN
from app.graph.prompts.constraints.emoji_ban import EMOJI_BAN
from app.graph.prompts.constraints.prompt_leak_ban import PROMPT_LEAK_BAN
from app.graph.prompts.constraints.table_ban import TABLE_BAN
from app.graph.prompts.persona.base_persona import BASE_PERSONA
from app.graph.prompts.persona.listening_persona import LISTENING_PERSONA
from app.graph.prompts.phases.feedback import FEEDBACK
from app.graph.prompts.phases.opening import OPENING, build_opening_prompt
from app.graph.prompts.phases.outline import OUTLINE
from app.graph.prompts.phases.polish import POLISH
from app.graph.prompts.phases.say import SAY, SAY_LISTENING
from app.graph.prompts.types import PromptTemplate

LISTENING_CONCEPTS = {"TIL", "회고"}

PHASE_ROLES = {
    "opening": "purpose",
    "say": "purpose",
    "feedback": "checkpoint",
    "outline": "generate",
    "polish": "generate",
}

PHASE_INSTRUCTIONS = {
    "opening": OPENING,
    "say": SAY,
    "feedback": FEEDBACK,
    "outline": OUTLINE,
    "polish": POLISH,
}

GLOBAL_CONSTRAINTS = [CHINESE_BAN, ASCII_DIAGRAM_BAN, EMOJI_BAN, TABLE_BAN, PROMPT_LEAK_BAN]


def get_concept_content(concept: str, phase: str) -> PromptTemplate:
    concept_key = concept.value if hasattr(concept, "value") else concept
    role = PHASE_ROLES[phase]
    return CONCEPT_TEMPLATES[concept_key][role]


def get_phase_instruction(concept: str, phase: str) -> PromptTemplate:
    concept_key = concept.value if hasattr(concept, "value") else concept
    if phase == "opening":
        return build_opening_prompt(concept)
    if phase == "say" and concept_key in LISTENING_CONCEPTS:
        return SAY_LISTENING
    return PHASE_INSTRUCTIONS[phase]


def get_persona(concept: str) -> PromptTemplate:
    concept_key = concept.value if hasattr(concept, "value") else concept
    if concept_key in LISTENING_CONCEPTS:
        return LISTENING_PERSONA
    return BASE_PERSONA


def build_system_prompt(
    concept: str,
    phase: str,
    *,
    topic: str,
    user_nickname: str | None = None,
    audience: str | None = None,
) -> str:
    persona = get_persona(concept)
    concept_content = get_concept_content(concept, phase)
    phase_template = get_phase_instruction(concept, phase)

    context = f"[주제] {topic}"
    if user_nickname:
        context += f"\n[사용자 닉네임] {user_nickname}"
    if audience:
        context += f"\n[독자 수준] {audience}"

    parts = [
        persona.text,
        *(constraint.text for constraint in GLOBAL_CONSTRAINTS),
        concept_content.text,
        phase_template.text,
        context,
    ]

    return "\n\n".join(parts)
