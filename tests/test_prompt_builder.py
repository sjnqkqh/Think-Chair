import pytest

from app.graph.prompts import (
    CONCEPT_TEMPLATES,
    GLOBAL_CONSTRAINTS,
    PHASE_INSTRUCTIONS,
    PHASE_ROLES,
    build_system_prompt,
    get_concept_content,
)
from app.graph.prompts.persona.base_persona import BASE_PERSONA
from app.graph.prompts.phases.outline import OUTLINE_FINAL_GUARD
from app.graph.prompts.phases.polish import POLISH_FINAL_GUARD
from app.graph.prompts.phases.say import SAY_DOCUMENT_GUARD


@pytest.mark.parametrize("concept", list(CONCEPT_TEMPLATES.keys()))
@pytest.mark.parametrize("phase", list(PHASE_INSTRUCTIONS.keys()))
def test_prompt_includes_persona_concept_and_phase(concept, phase):
    # 모든 컨셉 x 페이즈 조합에서 base_persona + concept 콘텐츠(역할별) + phase 지시문이 모두 포함되어야 한다.
    prompt = build_system_prompt(concept, phase, topic="테스트 주제")

    assert "존댓말" in prompt
    assert get_concept_content(concept, phase).text in prompt
    assert PHASE_INSTRUCTIONS[phase].text in prompt


@pytest.mark.parametrize("concept", list(CONCEPT_TEMPLATES.keys()))
@pytest.mark.parametrize("phase", list(PHASE_ROLES.keys()))
def test_concept_content_matches_phase_role(concept, phase):
    # get_concept_content는 PHASE_ROLES에 정의된 역할(purpose/checkpoint/generate)의 템플릿을 반환해야 한다.
    role = PHASE_ROLES[phase]
    assert get_concept_content(concept, phase) is CONCEPT_TEMPLATES[concept][role]


@pytest.mark.parametrize("concept", list(CONCEPT_TEMPLATES.keys()))
def test_purpose_is_nonempty(concept):
    # 모든 컨셉의 PURPOSE는 generate.md에서 추출된 비어있지 않은 텍스트여야 한다.
    assert CONCEPT_TEMPLATES[concept]["purpose"].text.strip()


def test_prompt_prohibits_chinese_characters():
    # 모든 프롬프트는 한자 사용 금지 문구를 포함해야 한다.
    prompt = build_system_prompt("딥다이브", "polish", topic="테스트 주제")

    assert "한자" in prompt


def test_prompt_includes_audience_when_provided():
    # audience가 주어지면 독자 수준 컨텍스트가 프롬프트에 포함되어야 한다.
    prompt = build_system_prompt(
        "수업 자료", "outline", topic="파이썬 기초", audience="초급"
    )

    assert "초급" in prompt


def test_prompt_omits_audience_context_when_not_provided():
    # audience가 없으면 독자 수준 컨텍스트 라인이 프롬프트에 나타나지 않아야 한다.
    prompt = build_system_prompt("에세이", "polish", topic="여행 이야기")

    assert "[독자 수준]" not in prompt


def test_opening_prompt_starts_with_topic_understanding_check():
    prompt = build_system_prompt("TIL", "opening", topic="FastAPI 학습")

    assert "대화 시작 단계" in prompt
    assert "단순한 인사" in prompt
    assert "얼마나 알고 있는지" in prompt
    assert "짧게 설명" in prompt
    assert "[주제] FastAPI 학습" in prompt


def test_prompt_prohibits_emoji():
    # 이모지 금지 제약도 항상 포함되어야 한다.
    prompt = build_system_prompt("에세이", "polish", topic="여행 이야기")

    assert "이모지" in prompt


def _all_templates():
    templates = [
        BASE_PERSONA,
        SAY_DOCUMENT_GUARD,
        OUTLINE_FINAL_GUARD,
        POLISH_FINAL_GUARD,
        *GLOBAL_CONSTRAINTS,
        *PHASE_INSTRUCTIONS.values(),
    ]
    for roles in CONCEPT_TEMPLATES.values():
        templates.extend(roles.values())
    return templates


@pytest.mark.parametrize("template", _all_templates(), ids=lambda t: t.id)
def test_every_template_documents_its_usage_context(template):
    # 모든 PromptTemplate은 향후 DB 이관을 대비해 used_when/description 메타데이터를 채워야 한다.
    assert template.id
    assert template.used_when.strip()
    assert template.description.strip()
