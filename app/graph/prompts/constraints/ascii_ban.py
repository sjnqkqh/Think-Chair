from app.graph.prompts.types import PromptTemplate

ASCII_DIAGRAM_BAN = PromptTemplate(
    id="constraint.ascii_diagram_ban",
    text="표나 그림을 텍스트/ASCII로 그리지 않습니다. 필요 시 마크다운 문법만 사용합니다.",
    used_when="모든 컨셉·모든 페이즈의 시스템 프롬프트에 항상 포함되는 전역 제약.",
    description="ASCII 표/그림 사용 금지 규칙. 실행 규칙에 의해 임의로 제거할 수 없다.",
)
