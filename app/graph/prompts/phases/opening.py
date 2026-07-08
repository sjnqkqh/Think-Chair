from app.graph.prompts.types import PromptTemplate

OPENING_QUESTION_BY_CONCEPT = {
    "딥다이브": "[사용자 닉네임]은 [주제]에 대해 얼마나 이해하고 있나요? 간단하게라도 설명해주세요.",
    "수업 자료": "[사용자 닉네임]은 [주제]에 대해 얼마나 이해하고 있나요? 간단하게라도 설명해주세요.",
    "TIL": "[사용자 닉네임]은 [주제]와 관련해 어떤 것을 배웠나요? 가볍게 설명해주세요.",
    "회고": "[사용자 닉네임]에게 [주제]는 어떤 경험이었나요? 가볍게 들려주세요.",
    "에세이": "[사용자 닉네임]에게 [주제]는 어떤 경험이었나요? 가볍게 들려주세요.",
}

OPENING = PromptTemplate(
    id="phase.opening",
    text="""지금은 대화 시작 단계입니다.
- 첫 응답은 반드시 아래 두 줄 형식으로만 출력하십시오.

안녕하세요, [사용자 닉네임]
오늘 [사용자 닉네임]과 함께 이야기할 주제는 '[주제]' 입니다. 
[오프닝 질문]

- [사용자 닉네임] 자리에는 시스템 프롬프트 하단의 [사용자 닉네임] 값을 그대로 넣으십시오.
- [주제] 자리에는 시스템 프롬프트 하단의 [주제] 값을 그대로 넣으십시오.
- [오프닝 질문] 자리에는 이 프롬프트에 지정된 질문 문장을 그대로 넣으십시오.
- 사용자의 첫 메시지가 "안녕하세요"처럼 단순한 인사뿐이어도 위 형식으로 응답하십시오.
- 위 두 줄 외의 잡담이나 안내성 덧붙임은 출력하지 마십시오.
- 개요, 초안, 원고 작성으로 넘어가자고 제안하지 마십시오.""",
    used_when="새 원고의 첫 사용자 메시지를 받은 직후, user_action == 'opening' 으로 opening_node가 호출될 때 사용된다.",
    description="첫 대화를 사용자 닉네임 인사, 주제 안내, 컨셉별 오프닝 질문으로 시작하기 위한 기본 지시문.",
)


def build_opening_prompt(concept: str) -> PromptTemplate:
    concept_key = concept.value if hasattr(concept, "value") else concept
    question = OPENING_QUESTION_BY_CONCEPT.get(
        concept_key,
        "[사용자 닉네임]은 [주제]에 대해 어떤 생각을 가지고 있나요? 가볍게 설명해주세요.",
    )
    return PromptTemplate(
        id=OPENING.id,
        text=OPENING.text.replace("[오프닝 질문]", question),
        used_when=OPENING.used_when,
        description=OPENING.description,
    )
