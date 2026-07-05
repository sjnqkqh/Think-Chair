from app.graph.prompts.types import PromptTemplate

FEEDBACK = PromptTemplate(
    id="phase.feedback",
    text="""지금은 피드백(feedback) 단계입니다.
- 위에 주어지는 이 컨셉의 점검 기준(체크리스트)을 기준으로, 지금까지의 대화 내용에 냉정하고 구체적인 피드백을 제공하십시오.
- 좋은 점과 부족한 점을 모두 짚되, 부족한 점은 어떻게 보완할지 구체적으로 제안하십시오.
- 아직 원고를 작성하지 마십시오.""",
    used_when="user_action == 'feedback' 로 feedback 노드가 호출될 때 사용된다.",
    description="피드백 단계 지시문.",
)
