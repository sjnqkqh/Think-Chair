import asyncio
import logging
import uuid
from collections.abc import AsyncIterator

from langchain_core.messages import AIMessageChunk
from langchain_core.messages import HumanMessage
from sqlalchemy import func
from sqlalchemy.exc import SQLAlchemyError

from app.models.chat import ChatMessage
from app.models.manuscript import Manuscript
from app.models.user import User
from app.services.storage.base import FileStorage

logger = logging.getLogger(__name__)

DOCUMENT_GENERATION_ACTIONS = {"outline", "polish"}
USER_VISIBLE_CHAT_NODES = {"opening", "converse", "feedback"}
DOCUMENT_GENERATION_ACK = (
    "문서 작성을 시작했습니다. 완료되면 오른쪽 문서 목록에 표시됩니다."
)


class ChatService:
    """LangGraph 그래프 실행과 채팅 응답 스트리밍을 담당한다.

    한 번의 채팅 턴은 두 단계로 나뉜다.
    1. begin_turn: 사용자 메시지를 저장하고 router 노드까지 그래프를 실행해 의도(action)를 판별
    2. stream_response: 판별된 action에 따라 남은 그래프를 실행하며 응답을 스트리밍
    """

    def __init__(self, graph, storage: FileStorage, db_factory):
        self.graph = graph
        self.storage = storage
        self.db_factory = db_factory
        # asyncio.create_task 결과를 참조하지 않으면 실행 중 가비지 컬렉션될 수 있다.
        self._background_tasks: set[asyncio.Task] = set()

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
        graph_run_config = self._build_graph_run_config(
            manuscript.id, model, request_db_session=database_session
        )
        state = await self.graph.ainvoke(
            self._input_state(manuscript, user, user_message, user_chat_message.id),
            config=graph_run_config,
            interrupt_after=["router"],
        )
        database_session.commit()
        action = state.get("user_action")
        if action in DOCUMENT_GENERATION_ACTIONS:
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
        yield "ready", {}

        if action in DOCUMENT_GENERATION_ACTIONS:
            self._start_document_generation(manuscript_id, model)
            yield "chunk", {"content": DOCUMENT_GENERATION_ACK}
            yield "done", {"document_generation": True}
        else:
            async for event_name, payload in self._stream_assistant_reply(
                manuscript_id, action, model
            ):
                yield event_name, payload

    async def _stream_assistant_reply(
        self,
        manuscript_id: uuid.UUID,
        action: str | None,
        model: str,
    ) -> AsyncIterator[tuple[str, dict]]:
        """남은 그래프를 실행하며 LLM 토큰을 스트리밍하고, 완성된 응답을 채팅 기록에 저장한다."""
        assistant_content = ""
        graph_run_config = self._build_graph_run_config(manuscript_id, model)
        async for chunk, metadata in self.graph.astream(
            None,
            config=graph_run_config,
            stream_mode="messages",
        ):
            if not self._should_stream_to_client(chunk, metadata):
                continue

            text = str(chunk.content or "")
            if text:
                assistant_content += text
                yield "chunk", {"content": text}

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
        yield "done", {}

    def _start_document_generation(self, manuscript_id: uuid.UUID, model: str) -> None:
        """문서 생성 그래프를 백그라운드 태스크로 실행한다. 결과는 그래프 노드가 직접 저장한다."""
        task = asyncio.create_task(self._run_document_generation(manuscript_id, model))
        self._background_tasks.add(task)
        task.add_done_callback(self._background_tasks.discard)

    async def _run_document_generation(
        self, manuscript_id: uuid.UUID, model: str = "default"
    ) -> None:
        graph_run_config = self._build_graph_run_config(manuscript_id, model)
        await self.graph.ainvoke(None, config=graph_run_config)

    def _build_graph_run_config(
        self, manuscript_id: uuid.UUID, model: str, request_db_session=None
    ):
        configurable = {
            "thread_id": str(manuscript_id),
            "model": model,
            "storage": self.storage,
            "db_factory": self.db_factory,
        }
        if request_db_session is not None:
            configurable["db_session"] = request_db_session

        return {"configurable": configurable}

    @staticmethod
    def _should_stream_to_client(chunk, metadata: dict) -> bool:
        return (
            isinstance(chunk, AIMessageChunk)
            and metadata.get("ls_integration") == "langchain_chat_model"
            and metadata.get("langgraph_node") in USER_VISIBLE_CHAT_NODES
        )

    @staticmethod
    def _input_state(
        manuscript: Manuscript,
        user: User | None,
        user_message: str,
        user_message_id: uuid.UUID,
    ) -> dict:
        """새 턴을 시작할 때 그래프에 넘길 입력 상태를 만든다."""
        return {
            "manuscript_id": str(manuscript.id),
            "concept": manuscript.concept.value,
            "topic": manuscript.topic,
            "user_nickname": user.nickname if user else None,
            "audience_level": manuscript.audience_level,
            "user_action": None,
            "current_message_id": str(user_message_id),
            "messages": [HumanMessage(content=user_message)],
            "client_message": None,
            "new_paper": None,
        }

    @staticmethod
    def _save_chat_message(
        database_session,
        manuscript: Manuscript,
        role: str,
        content: str,
        phase: str | None,
    ) -> ChatMessage:
        """채팅 기록 저장. 저장에 실패해도 예외를 삼키고 in-memory 메시지를 반환한다."""
        message = ChatMessage(
            id=uuid.uuid4(),
            manuscript_id=manuscript.id,
            role=role,
            content=content,
            phase=phase,
            sequence=1,
        )
        try:
            last_sequence = (
                database_session.query(func.max(ChatMessage.sequence))
                .filter(ChatMessage.manuscript_id == manuscript.id)
                .scalar()
            )
            message.sequence = (last_sequence or 0) + 1
            database_session.add(message)
            database_session.commit()
        except SQLAlchemyError:
            logger.exception(
                "채팅 기록 저장 실패 (manuscript_id=%s, role=%s)", manuscript.id, role
            )
            database_session.rollback()
        return message
