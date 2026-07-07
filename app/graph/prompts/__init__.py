from app.graph.prompts.concepts import CONCEPT_TEMPLATES
from app.graph.prompts.constraints.ascii_ban import ASCII_DIAGRAM_BAN
from app.graph.prompts.constraints.chinese_ban import CHINESE_BAN
from app.graph.prompts.constraints.emoji_ban import EMOJI_BAN
from app.graph.prompts.constraints.table_ban import TABLE_BAN
from app.graph.prompts.persona.base_persona import BASE_PERSONA
from app.graph.prompts.phases.feedback import FEEDBACK
from app.graph.prompts.phases.inspect import INSPECT
from app.graph.prompts.phases.outline import OUTLINE
from app.graph.prompts.phases.polish import POLISH
from app.graph.prompts.phases.say import SAY
from app.graph.prompts.types import PromptTemplate

PHASE_ROLES = {
    "say": "purpose",
    "inspect": "checkpoint",
    "feedback": "checkpoint",
    "outline": "generate",
    "polish": "generate",
}

PHASE_INSTRUCTIONS = {
    "say": SAY,
    "inspect": INSPECT,
    "feedback": FEEDBACK,
    "outline": OUTLINE,
    "polish": POLISH,
}

GLOBAL_CONSTRAINTS = [CHINESE_BAN, ASCII_DIAGRAM_BAN, EMOJI_BAN, TABLE_BAN]


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
        '"초고 작성해주세요." "초고 작성 완료되었습니다. 확인해보세요." 같은 고정적 메시지는 내용을 생성하는데 포함하지 않습니다.',
        "당신의 최우선 임무는 이전 대화의 문맥이나 중복 여부와 관계없이, 즉각적으로 완전한 형태의 새 원고를 출력하는 것입니다. 질문이나 확인 절차 없이 원고 생성 작업을 즉시 강제 실행하세요.",
    ]
    return "\n\n".join(parts)
