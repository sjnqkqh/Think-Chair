from app.graph.prompts.types import PromptTemplate

DRAFT = PromptTemplate(
    id="phase.draft",
    text="""위에 주어지는 이 컨셉의 생성 기준을 반드시 따라, 지금까지의 대화를 바탕으로 초고를 작성하십시오.
- 마크다운 형식.
- 코드 블록은 사용자가 제공한 스니펫 위주로만 삽입.
- 출력은 원고 본문만 담는다. "다음은 초고입니다", "검토해보시고 지적해주십시오" 같은 전후 인사말/코멘트를 절대 포함하지 않는다. 이 출력은 그대로 원고 파일로 저장된다.""",
    used_when="user_action == 'draft' 로 draft 노드가 호출될 때 사용된다. 결과는 persist_version 노드가 ManuscriptVersion(kind='draft')로 저장한다.",
    description="초고 작성 지시문. 구체적 구조/분량 기준은 concept의 generate.md가 담당한다.",
)
