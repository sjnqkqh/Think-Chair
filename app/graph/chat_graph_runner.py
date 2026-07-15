import uuid
from collections.abc import AsyncIterator

from langchain_core.messages import AIMessageChunk, HumanMessage

from app.models.manuscript import Manuscript
from app.models.user import User

USER_VISIBLE_CHAT_NODES = {"opening", "converse", "feedback"}


class ChatGraphRunner:
    def __init__(self, graph, storage, db_factory):
        self._graph = graph
        self._storage = storage
        self._db_factory = db_factory

    async def route_turn(
        self,
        manuscript: Manuscript,
        user: User | None,
        user_message: str,
        user_message_id: uuid.UUID,
        request_db_session,
        model: str,
    ) -> dict:
        return await self._graph.ainvoke(
            _initial_turn_state(manuscript, user, user_message, user_message_id),
            config=self._run_config(
                manuscript.id, model, request_db_session=request_db_session
            ),
            interrupt_after=["router"],
        )

    async def stream_reply_tokens(
        self, manuscript_id: uuid.UUID, model: str
    ) -> AsyncIterator[str]:
        async for chunk, metadata in self._graph.astream(
            None,
            config=self._run_config(manuscript_id, model),
            stream_mode="messages",
        ):
            if not _should_stream_to_client(chunk, metadata):
                continue

            text = str(chunk.content or "")
            if text:
                yield text

    async def run_document_generation(
        self, manuscript_id: uuid.UUID, model: str
    ) -> None:
        await self._graph.ainvoke(None, config=self._run_config(manuscript_id, model))

    def _run_config(
        self, manuscript_id: uuid.UUID, model: str, request_db_session=None
    ):
        configurable = {
            "thread_id": str(manuscript_id),
            "model": model,
            "storage": self._storage,
            "db_factory": self._db_factory,
        }
        if request_db_session is not None:
            configurable["db_session"] = request_db_session

        return {"configurable": configurable}


def _should_stream_to_client(chunk, metadata: dict) -> bool:
    return (
        isinstance(chunk, AIMessageChunk)
        and metadata.get("ls_integration") == "langchain_chat_model"
        and metadata.get("langgraph_node") in USER_VISIBLE_CHAT_NODES
    )


def _initial_turn_state(
    manuscript: Manuscript,
    user: User | None,
    user_message: str,
    user_message_id: uuid.UUID,
) -> dict:
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
