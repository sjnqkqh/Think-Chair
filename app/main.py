import logging
import os
from contextlib import AsyncExitStack, asynccontextmanager

import app.models.user
from fastapi import FastAPI

from app.api.endpoints import router as api_router
from app.core.config import settings
from app.core.database import Base, SessionLocal, engine
from app.core.error_handlers import register_exception_handlers
from app.graph import llm_registry
from app.graph.builder import build_graph
from app.graph.checkpointer import make_checkpointer
from app.pages.auth_pages import router as auth_pages_router
from app.pages.chat_pages import router as chat_pages_router
from app.pages.user_interface import router as pages_router
from app.services.chat_service import ChatService
from app.services.storage.local import LocalFileStorage

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
        checkpointer = await stack.enter_async_context(make_checkpointer(checkpoint_path))
        graph = build_graph(checkpointer)
        app.state.chat_service = ChatService(
            graph=graph, storage=LocalFileStorage(), db_factory=SessionLocal
        )
        yield


app = FastAPI(
    title="RAG FastAPI Server",
    description="RAG 기능을 포함한 챗봇 서버",
    version="2.0.0",
    lifespan=lifespan,
)

register_exception_handlers(app)

# Register API routes
app.include_router(api_router)
app.include_router(pages_router)
app.include_router(auth_pages_router)
app.include_router(chat_pages_router)
