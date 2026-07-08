from langchain_core.messages import HumanMessage
from langchain_core.messages import AIMessage
from sqlalchemy import func

from app.models.chat import ChatMessage
from app.models.manuscript import Manuscript
from app.models.user import User
from app.services.storage.base import FileStorage


class ChatService:
    def __init__(self, graph, storage: FileStorage, db_factory):
        self.graph = graph
        self.storage = storage
        self.db_factory = db_factory

    async def run(
        self,
        manuscript: Manuscript,
        user_message: str,
        model: str = "default",
    ) -> dict:
        with self.db_factory() as db:
            user = db.get(User, manuscript.user_id)
            user_chat_message = self._add_chat_message(
                db,
                manuscript=manuscript,
                role="user",
                content=user_message,
                phase=None,
            )
            db.flush()
            config = {
                "configurable": {
                    "thread_id": str(manuscript.id),
                    "model": model,
                    "storage": self.storage,
                    "db_session": db,
                }
            }

            input_state = {
                "manuscript_id": str(manuscript.id),
                "concept": manuscript.concept.value,
                "topic": manuscript.topic,
                "user_nickname": user.nickname if user else None,
                "audience_level": manuscript.audience_level,
                "user_action": None,
                "current_message_id": str(user_chat_message.id),
                "messages": [HumanMessage(content=user_message)],
                "pending_version": None,
            }

            state = await self.graph.ainvoke(input_state, config=config)
            ai_message = next(
                msg for msg in reversed(state["messages"]) if isinstance(msg, AIMessage)
            )
            self._add_chat_message(
                db,
                manuscript=manuscript,
                role="assistant",
                content=str(ai_message.content),
                phase=state.get("user_action"),
            )
            db.commit()
            return state

    @staticmethod
    def _add_chat_message(
        db,
        manuscript: Manuscript,
        role: str,
        content: str,
        phase: str | None,
    ) -> ChatMessage:
        last_sequence = (
            db.query(func.max(ChatMessage.sequence))
            .filter(ChatMessage.manuscript_id == manuscript.id)
            .scalar()
        )
        message = ChatMessage(
            manuscript_id=manuscript.id,
            role=role,
            content=content,
            phase=phase,
            sequence=(last_sequence or 0) + 1,
        )
        db.add(message)
        return message
