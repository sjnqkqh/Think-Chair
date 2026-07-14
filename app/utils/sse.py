from enum import StrEnum


class SseEvent(StrEnum):
    """SSE 스트림에서 클라이언트로 내보내는 이벤트 이름."""

    READY = "ready"
    CHUNK = "chunk"
    DONE = "done"
    ERROR = "error"
