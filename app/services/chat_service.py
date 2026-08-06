import uuid
from collections.abc import AsyncIterator
from dataclasses import dataclass

from app.graph import llm_registry
from app.graph.chat_graph_runner import ChatGraphRunner
from app.models.chat import ChatMessage
from app.models.manuscript import Manuscript
from app.models.research import ResearchJob
from app.models.user import User
from app.repositories import chat_repo
from app.research.evidence_need import detect_evidence_need
from app.research.research_eligibility import concept_allows_web_research
from app.services.background_tasks import BackgroundTaskRegistry
from app.utils.sse import SseEvent

DOCUMENT_GENERATION_ACTIONS = {"outline", "generate_document"}
DOCUMENT_GENERATION_ACK = (
    "문서 작성을 시작했습니다. 완료되면 오른쪽 문서 목록에 표시됩니다."
)
# 이 액션들은 사용자 주장을 근거로 검증하는 대화 턴이 아니라서 조사를 걸지 않는다.
NON_RESEARCH_ACTIONS = {
    "feedback",
    "outline",
    "generate_document",
    "refuse",
    "opening",
}


@dataclass(frozen=True)
class TurnStart:
    action: str | None
    message_id: uuid.UUID
    research_required: bool
    claim_or_query: str | None


def is_document_generation(action: str | None) -> bool:
    return action in DOCUMENT_GENERATION_ACTIONS


def list_chat_messages(database_session, manuscript_id: uuid.UUID) -> list[ChatMessage]:
    return chat_repo.list_messages(database_session, manuscript_id)


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
        *,
        provider: str | None = None,
        model: str | None = None,
        effort: str | None = None,
    ) -> TurnStart:
        """사용자 메시지를 기록하고 router 노드까지 그래프를 실행해 action을 반환한다."""
        model_key = llm_registry.resolve_model_key(
            provider=provider, model=model, effort=effort
        )
        user = database_session.get(User, manuscript.user_id)
        user_chat_message = self._save_chat_message(
            database_session,
            manuscript=manuscript,
            role="user",
            content=user_message,
            phase=None,
        )
        evidence_text = None
        if concept_allows_web_research(manuscript.concept):
            from app.research.turn_evidence import load_evidence_text_for_turn

            evidence_text = load_evidence_text_for_turn(
                user_id=manuscript.user_id,
                manuscript_id=manuscript.id,
                query=user_message,
            ) or None
        state = await self.graph_runner.route_turn(
            manuscript=manuscript,
            user=user,
            user_message=user_message,
            user_message_id=user_chat_message.id,
            request_db_session=database_session,
            model=model_key,
            evidence_text=evidence_text,
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
            database_session.commit()
            return TurnStart(
                action=action,
                message_id=user_chat_message.id,
                research_required=False,
                claim_or_query=None,
            )

        research_required = False
        claim_or_query = None
        if (
            action not in NON_RESEARCH_ACTIONS
            and concept_allows_web_research(manuscript.concept)
        ):
            evidence_need = detect_evidence_need(user_message)
            if evidence_need.required:
                from app.research.turn_evidence import evidence_sufficient_for_turn

                already_sufficient = evidence_sufficient_for_turn(
                    user_id=manuscript.user_id,
                    manuscript_id=manuscript.id,
                    query=user_message,
                )
                if not already_sufficient:
                    research_required = True
                    claim_or_query = evidence_need.claim_or_query

        return TurnStart(
            action=action,
            message_id=user_chat_message.id,
            research_required=research_required,
            claim_or_query=claim_or_query,
        )

    async def stream_response(
        self,
        manuscript_id: uuid.UUID,
        action: str | None,
        *,
        provider: str | None = None,
        model: str | None = None,
        effort: str | None = None,
        research_required: bool = False,
    ) -> AsyncIterator[tuple[str, dict]]:
        """action에 따라 (이벤트 이름, 페이로드) 쌍을 스트리밍한다.

        research_required면 조사가 끝날 때까지 답변을 스트리밍하지 않는다.
        조사 완료 후 답변은 stream_grounded_reply_after_research가 같은 턴에 이어 보낸다.
        """
        yield SseEvent.READY, {}
        model_key = llm_registry.resolve_model_key(
            provider=provider, model=model, effort=effort
        )

        if is_document_generation(action):
            self._start_document_generation(manuscript_id, model_key)
            yield SseEvent.CHUNK, {"content": DOCUMENT_GENERATION_ACK}
            yield SseEvent.DONE, {"document_generation": True}
        elif research_required:
            yield SseEvent.DONE, {"awaiting_research": True}
        else:
            async for event_name, payload in self._stream_assistant_reply(
                manuscript_id, action, model_key
            ):
                yield event_name, payload

    async def stream_grounded_reply_after_research(
        self,
        manuscript: Manuscript,
        job: ResearchJob,
        *,
        provider: str | None = None,
        model: str | None = None,
        effort: str | None = None,
    ) -> AsyncIterator[tuple[str, dict]]:
        """조사가 끝난 뒤, 같은 사용자 메시지에 근거를 반영한 답변을 이어 스트리밍한다.

        begin_turn을 다시 호출하지 않으므로 사용자 메시지를 중복 저장하지 않는다.
        """
        yield SseEvent.READY, {}
        model_key = llm_registry.resolve_model_key(
            provider=provider, model=model, effort=effort
        )

        query = (job.claim_or_query or "").strip()
        if query:
            from app.research.turn_evidence import load_evidence_text_for_turn

            evidence_text = (
                load_evidence_text_for_turn(
                    user_id=manuscript.user_id,
                    manuscript_id=manuscript.id,
                    query=query,
                )
                or None
            )
            await self.graph_runner.update_evidence_text(
                manuscript.id, model_key, evidence_text
            )

        async for event_name, payload in self._stream_assistant_reply(
            manuscript.id, "say", model_key
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
        return chat_repo.create_message(
            database_session,
            manuscript=manuscript,
            role=role,
            content=content,
            phase=phase,
        )
