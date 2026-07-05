from app.graph.prompts.types import PromptTemplate

POLISH = PromptTemplate(
    id="phase.polish",
    text="""위에 주어지는 이 컨셉의 생성 기준을 반드시 따라, 지금까지의 초고와 대화를 바탕으로 탈고(polish)된 최종본을 작성하십시오.
- 문장을 다듬고, 중복되거나 불필요한 부분을 제거하십시오.
- 원고 전체의 구조와 흐름은 유지하십시오.
- 마크다운 형식.
- 출력은 원고 본문만 담는다. "다음은 최종본입니다", "검토해보시고 지적해주십시오" 같은 전후 인사말/코멘트를 절대 포함하지 않는다. 이 출력은 그대로 원고 파일로 저장된다.""",
    used_when="user_action == 'polish' 로 polish 노드가 호출될 때 사용된다. 결과는 persist_version 노드가 ManuscriptVersion(kind='polish')로 저장한다.",
    description="탈고 지시문. 구체적 구조/분량 기준은 concept의 generate.md가 담당한다.",
)
