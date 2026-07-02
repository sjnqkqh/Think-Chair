from app.graph.prompts.types import PromptTemplate

DRAFT = PromptTemplate(
    id="phase.draft",
    text="""위에 주어지는 이 컨셉의 생성 기준을 반드시 따라, 지금까지의 대화를 바탕으로 초고를 작성하십시오.
- 마크다운 형식.
- 코드 블록은 사용자가 제공한 스니펫 위주로만 삽입.""",
    used_when="user_action == 'draft' 로 draft 노드가 호출될 때 사용된다. 결과는 persist_version 노드가 ManuscriptVersion(kind='draft')로 저장한다.",
    description="초고 작성 지시문. 구체적 구조/분량 기준은 concept의 generate.md가 담당한다.",
)
