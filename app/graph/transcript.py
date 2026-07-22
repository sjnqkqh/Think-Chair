from langchain_core.messages import AIMessage, BaseMessage, HumanMessage

_ROLE_LABELS = {HumanMessage: "사용자", AIMessage: "AI"}


def render_transcript(messages: list[BaseMessage]) -> str:
    """역할 라벨이 붙은 대화 전문을 반환한다.

    메타 판단 노드(게이트/거절)가 대화를 라이브 채팅 턴으로 재생하면 모델이 마지막
    '문서 작성' 요청에 순응해 문서를 생성해버린다. 이를 막기 위해 대화를 참조 텍스트로
    임베드한다.
    """
    transcript_lines = []
    for message in messages:
        label = _ROLE_LABELS.get(type(message))
        if label is None:
            continue
        message_content = str(message.content or "").strip()
        if message_content:
            transcript_lines.append(f"{label}: {message_content}")
    return "\n".join(transcript_lines)
