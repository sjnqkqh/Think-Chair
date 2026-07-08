import pytest

from app.graph.prompts import (
    CONCEPT_TEMPLATES,
    GLOBAL_CONSTRAINTS,
    PHASE_INSTRUCTIONS,
    PHASE_ROLES,
    build_system_prompt,
    get_concept_content,
    get_phase_instruction,
    get_persona,
)
from app.graph.prompts.persona.base_persona import BASE_PERSONA
from app.graph.prompts.persona.listening_persona import LISTENING_PERSONA
from app.graph.prompts.phases.outline import OUTLINE_FINAL_GUARD
from app.graph.prompts.phases.polish import POLISH_FINAL_GUARD
from app.graph.prompts.phases.say import SAY_DOCUMENT_GUARD, SAY_LISTENING


@pytest.mark.parametrize("concept", list(CONCEPT_TEMPLATES.keys()))
@pytest.mark.parametrize("phase", list(PHASE_INSTRUCTIONS.keys()))
def test_prompt_includes_persona_concept_and_phase(concept, phase):
    # 모든 컨셉 x 페이즈 조합에서 컨셉별 persona + concept 콘텐츠(역할별) + phase 지시문이 모두 포함되어야 한다.
    prompt = build_system_prompt(concept, phase, topic="테스트 주제")

    assert "존댓말" in prompt
    assert get_persona(concept).text in prompt
    assert get_concept_content(concept, phase).text in prompt
    assert get_phase_instruction(concept, phase).text in prompt


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


@pytest.mark.parametrize("concept", ["회고", "TIL"])
def test_listening_concepts_use_listening_persona(concept):
    prompt = build_system_prompt(concept, "say", topic="테스트 주제")

    assert LISTENING_PERSONA.text in prompt
    assert BASE_PERSONA.text not in prompt
    assert "학생이 겪은 기술적 경험, 시행착오, 감정, 배운 점" in prompt
    assert "빈틈을 찾아 질문한다" not in prompt
    assert "내용이 충분히 쌓인 후" not in prompt


@pytest.mark.parametrize("concept", ["딥다이브", "수업 자료"])
def test_technical_exploration_concepts_keep_base_persona(concept):
    prompt = build_system_prompt(concept, "say", topic="테스트 주제")

    assert BASE_PERSONA.text in prompt
    assert LISTENING_PERSONA.text not in prompt
    assert "빈틈을 찾아 질문한다" in prompt


@pytest.mark.parametrize("concept", ["회고", "TIL"])
def test_listening_concepts_use_listening_say_phase(concept):
    prompt = build_system_prompt(concept, "say", topic="테스트 주제")

    assert SAY_LISTENING.text in prompt
    assert "매 응답마다 질문하지 마십시오" in prompt


def test_deepdive_keeps_question_oriented_say_phase():
    prompt = build_system_prompt("딥다이브", "say", topic="테스트 주제")

    assert SAY_LISTENING.text not in prompt
    assert "자연스럽게 질문을 이어가십시오" in prompt


@pytest.mark.parametrize(
    ("concept", "expected", "unexpected"),
    [
        ("딥다이브", "얼마나 이해하고 있나요? 간단하게라도 설명해주세요", "어떤 것을 배웠나요"),
        ("수업 자료", "얼마나 이해하고 있나요? 간단하게라도 설명해주세요", "어떤 경험이었나요"),
        ("TIL", "어떤 것을 배웠나요? 가볍게 설명해주세요", "얼마나 이해하고 있나요"),
        ("회고", "어떤 경험이었나요? 가볍게 들려주세요", "어떤 것을 배웠나요"),
        ("에세이", "어떤 경험이었나요? 가볍게 들려주세요", "얼마나 이해하고 있나요"),
    ],
)
def test_opening_prompt_uses_concept_specific_question(concept, expected, unexpected):
    prompt = build_system_prompt(
        concept, "opening", topic="FastAPI 학습", user_nickname="테스터"
    )

    assert "대화 시작 단계" in prompt
    assert "안녕하세요, [사용자 닉네임]" in prompt
    assert "오늘 [사용자 닉네임]과 함께 이야기할 주제는 '[주제]' 입니다" in prompt
    assert expected in prompt
    assert unexpected not in prompt
    assert "반갑습니다" not in prompt
    assert "[주제] FastAPI 학습" in prompt
    assert "[사용자 닉네임] 테스터" in prompt


def test_prompt_prohibits_emoji():
    # 이모지 금지 제약도 항상 포함되어야 한다.
    prompt = build_system_prompt("에세이", "polish", topic="여행 이야기")

    assert "이모지" in prompt


def _all_templates():
    templates = [
        BASE_PERSONA,
        LISTENING_PERSONA,
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
