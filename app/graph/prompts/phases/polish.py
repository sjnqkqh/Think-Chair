from app.graph.prompts.types import PromptTemplate

POLISH = PromptTemplate(
    id="phase.polish",
    text="""위에 주어지는 이 컨셉의 생성 기준을 반드시 따라, 지금까지의 초고와 대화를 바탕으로 탈고(polish)된 최종본을 작성하십시오.
- 문장을 다듬고, 중복되거나 불필요한 부분을 제거하십시오.
- 원고 전체의 구조와 흐름은 유지하십시오.
- 마크다운 형식.""",
    used_when="user_action == 'polish' 로 polish 노드가 호출될 때 사용된다. 결과는 persist_version 노드가 ManuscriptVersion(kind='polish')로 저장한다.",
    description="탈고 지시문. 구체적 구조/분량 기준은 concept의 generate.md가 담당한다.",
)
