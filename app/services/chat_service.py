import uuid
from collections.abc import AsyncIterator

from sqlalchemy.exc import SQLAlchemyError

from app.graph.chat_graph_runner import ChatGraphRunner
from app.logging import get_logger
from app.models.chat import ChatMessage
from app.models.manuscript import Manuscript
from app.models.user import User
from app.repositories import chat_repo
from app.services.background_tasks import BackgroundTaskRegistry
from app.utils.sse import SseEvent

logger = get_logger(__name__)

DOCUMENT_GENERATION_ACTIONS = {"outline", "polish"}
DOCUMENT_GENERATION_ACK = (
    "문서 작성을 시작했습니다. 완료되면 오른쪽 문서 목록에 표시됩니다."
)


def is_document_generation(action: str | None) -> bool:
    return action in DOCUMENT_GENERATION_ACTIONS


class ChatService:
    """채팅 턴 처리와 응답 스트리밍 정책을 담당한다.

    한 번의 채팅 턴은 두 단계로 나뉜다.
    1. begin_turn: 사용자 메시지를 저장하고 router 노드까지 그래프를 실행해 의도(action)를 판별
    2. stream_response: 판별된 action에 따라 남은 그래프를 실행하며 응답을 스트리밍
    """

    def __init__(
        self,
        graph_runner: ChatGraphRunner,
        db_factory,
        background_tasks: BackgroundTaskRegistry,
    ):
        self.graph_runner = graph_runner
        self.db_factory = db_factory
        self.background_tasks = background_tasks

    async def begin_turn(
        self,
        database_session,
        manuscript: Manuscript,
        user_message: str,
        model: str = "default",
    ) -> str | None:
        """사용자 메시지를 기록하고 router 노드까지 그래프를 실행해 action을 반환한다."""
        user = database_session.get(User, manuscript.user_id)
        user_chat_message = self._save_chat_message(
            database_session,
            manuscript=manuscript,
            role="user",
            content=user_message,
            phase=None,
        )
        state = await self.graph_runner.route_turn(
            manuscript=manuscript,
            user=user,
            user_message=user_message,
            user_message_id=user_chat_message.id,
            request_db_session=database_session,
            model=model,
        )
        database_session.commit()
        action = state.get("user_action")
        if is_document_generation(action):
            self._save_chat_message(
                database_session,
                manuscript=manuscript,
                role="assistant",
                content=DOCUMENT_GENERATION_ACK,
                phase=action,
            )
        return action

    async def stream_response(
        self,
        manuscript_id: uuid.UUID,
        action: str | None,
        model: str = "default",
    ) -> AsyncIterator[tuple[str, dict]]:
        """action에 따라 (이벤트 이름, 페이로드) 쌍을 스트리밍한다."""
        yield SseEvent.READY, {}

        if is_document_generation(action):
            self._start_document_generation(manuscript_id, model)
            yield SseEvent.CHUNK, {"content": DOCUMENT_GENERATION_ACK}
            yield SseEvent.DONE, {"document_generation": True}
        else:
            async for event_name, payload in self._stream_assistant_reply(
                manuscript_id, action, model
            ):
                yield event_name, payload

    def _start_document_generation(
        self, manuscript_id: uuid.UUID, model: str = "default"
    ) -> None:
        self.background_tasks.start(
            self.graph_runner.run_document_generation(manuscript_id, model)
        )

    async def _stream_assistant_reply(
        self,
        manuscript_id: uuid.UUID,
        action: str | None,
        model: str = "default",
    ) -> AsyncIterator[tuple[str, dict]]:
        """남은 그래프를 실행하며 LLM 토큰을 스트리밍하고, 완성된 응답을 채팅 기록에 저장한다."""
        assistant_content = ""
        async for text in self.graph_runner.stream_reply_tokens(manuscript_id, model):
            assistant_content += text
            yield SseEvent.CHUNK, {"content": text}

        with self.db_factory() as database_session:
            manuscript = database_session.get(Manuscript, manuscript_id)
            if manuscript and assistant_content:
                self._save_chat_message(
                    database_session,
                    manuscript=manuscript,
                    role="assistant",
                    content=assistant_content,
                    phase=action,
                )
        yield SseEvent.DONE, {}

    @staticmethod
    def _save_chat_message(
        database_session,
        manuscript: Manuscript,
        role: str,
        content: str,
        phase: str | None,
    ) -> ChatMessage:
        """채팅 기록 저장. 감사/분석용 로그이므로 저장에 실패해도 예외를 삼키고
        in-memory 메시지를 반환해 진행 중인 턴을 깨뜨리지 않는다."""
        try:
            return chat_repo.create_message(
                database_session,
                manuscript=manuscript,
                role=role,
                content=content,
                phase=phase,
            )
        except SQLAlchemyError:
            logger.exception(
                "chat_message.save_failed", manuscript_id=manuscript.id, role=role
            )
            database_session.rollback()
            return ChatMessage(
                id=uuid.uuid4(),
                manuscript_id=manuscript.id,
                role=role,
                content=content,
                phase=phase,
                sequence=1,
            )
