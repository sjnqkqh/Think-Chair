from langchain_core.messages import HumanMessage

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
                "messages": [HumanMessage(content=user_message)],
                "pending_version": None,
            }

            return await self.graph.ainvoke(input_state, config=config)
