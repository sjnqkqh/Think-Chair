import uuid


class ConversationStateReader:
    def __init__(self, graph):
        self._graph = graph

    async def load_messages(self, manuscript_id: uuid.UUID) -> list:
        config = {"configurable": {"thread_id": str(manuscript_id)}}
        snapshot = await self._graph.aget_state(config)
        return snapshot.values.get("messages", []) if snapshot and snapshot.values else []
