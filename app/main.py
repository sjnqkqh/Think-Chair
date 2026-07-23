import logging
import os
from contextlib import AsyncExitStack, asynccontextmanager

import app.models
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.api.endpoints import router as api_router
from app.core.config import settings
from app.core.database import Base, SessionLocal, engine
from app.core.error_handlers import register_exception_handlers
from app.core.storage import get_file_storage
from app.graph import llm_registry
from app.graph.builder import build_graph
from app.graph.chat_graph_runner import ChatGraphRunner
from app.graph.checkpointer import make_checkpointer
from app.graph.conversation_state import ConversationStateReader
from app.pages.auth_pages import router as auth_pages_router
from app.pages.debug_pages import router as debug_pages_router
from app.pages.workspace_pages import router as workspace_pages_router
from app.services.background_tasks import BackgroundTaskRegistry
from app.services.chat_service import ChatService

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s - %(message)s"
)

# Create database tables
Base.metadata.create_all(bind=engine)

llm_registry.bootstrap(settings)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # LangGraph 체크포인터는 앱 생명주기 동안 열려있어야 하므로 AsyncExitStack으로 관리한다.
    async with AsyncExitStack() as stack:
        checkpoint_path = os.path.join(settings.BASE_DIR, "draftsmith_checkpoint.db")
        checkpointer = await stack.enter_async_context(
            make_checkpointer(checkpoint_path)
        )
        graph = build_graph(checkpointer)
        app.state.graph = graph
        graph_runner = ChatGraphRunner(
            graph=graph, storage=get_file_storage(), db_factory=SessionLocal
        )
        chat_service = ChatService(
            graph_runner=graph_runner,
            db_factory=SessionLocal,
            background_tasks=BackgroundTaskRegistry(),
        )
        app.state.chat_service = chat_service
        app.state.conversation_state = ConversationStateReader(graph)
        yield


app = FastAPI(
    title="Think Chair FastAPI Server",
    description="AI 글쓰기 협업 워크스페이스 서버",
    version="2.0.0",
    lifespan=lifespan,
)

register_exception_handlers(app)

app.mount(
    "/static/common",
    StaticFiles(
        directory=os.path.join(settings.BASE_DIR, "app", "templates", "common")
    ),
    name="static-common",
)

# Register API routes
app.include_router(api_router)
app.include_router(auth_pages_router)
app.include_router(debug_pages_router)
app.include_router(workspace_pages_router)
