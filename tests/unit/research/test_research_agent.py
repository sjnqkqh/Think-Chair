from datetime import datetime, timezone
from typing import Any
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from pydantic import Field, PrivateAttr
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.models.manuscript import ConceptType, Manuscript, ManuscriptStatus
from app.models.research import ResearchUsage
from app.models.user import User
from app.research.contracts import (
    FetchResponse,
    FetchedSource,
    ResearchIndexRequest,
    ResearchIndexResult,
    SearchHit,
    SearchRequest,
    SearchResponse,
)
from app.research.research_agent import clip_search_query, run_research_agent
from tests.db_setup import prepare_test_database

pytestmark = pytest.mark.unit


class ScriptedChatModel(BaseChatModel):
    """bind_tools를 지원하는 테스트용 스크립트 모델."""

    responses: list[AIMessage] = Field(default_factory=list)
    _index: int = PrivateAttr(default=0)

    @property
    def _llm_type(self) -> str:
        return "scripted"

    def bind_tools(self, tools: Any, **kwargs: Any) -> "ScriptedChatModel":
        copy = self.model_copy(deep=True)
        copy.responses = list(self.responses)
        copy._index = self._index
        return copy

    def _generate(self, messages, stop=None, run_manager=None, **kwargs):
        message = self.responses[min(self._index, len(self.responses) - 1)]
        self._index += 1
        return ChatResult(generations=[ChatGeneration(message=message)])

    async def _agenerate(self, messages, stop=None, run_manager=None, **kwargs):
        return self._generate(messages, stop=stop, run_manager=run_manager, **kwargs)


def _tool_call(name: str, args: dict, call_id: str) -> dict:
    return {"name": name, "args": args, "id": call_id, "type": "tool_call"}


def _fetched(url: str) -> FetchedSource:
    return FetchedSource(
        requested_url=url,
        canonical_url=url,
        title="Doc",
        publisher="Example",
        published_at="2026-01-01",
        text=("timeout is 360 minutes. " * 20),
        sections=[],
        media_type="text/html",
        fetched_at=datetime.now(timezone.utc),
        content_hash="hash",
        source_key="key",
    )


@pytest.mark.asyncio
async def test_agent_blocks_disallowed_fetch_without_http_call(monkeypatch):
    monkeypatch.setattr(
        "app.research.research_agent.research_repo.increment_research_search_count",
        lambda *args, **kwargs: None,
    )
    fetch = AsyncMock()
    search = AsyncMock(
        return_value=SearchResponse(
            results=[
                SearchHit(
                    url="https://evil.example/page",
                    title="Evil",
                    snippet="x",
                    provider_rank=1,
                )
            ]
        )
    )
    model = ScriptedChatModel(
        responses=[
            AIMessage(
                content="",
                tool_calls=[
                    _tool_call("fetch_page", {"url": "https://evil.example/page"}, "1")
                ],
            ),
            AIMessage(
                content="",
                tool_calls=[_tool_call("finish_research", {"reason": "blocked"}, "2")],
            ),
            AIMessage(content="done"),
        ]
    )
    job = type("Job", (), {"id": uuid4(), "user_id": uuid4(), "manuscript_id": uuid4()})()

    error = await run_research_agent(
        db=type("Db", (), {"commit": lambda self: None})(),
        job=job,
        query="claim",
        evidence_index=object(),
        storage=object(),
        embeddings=object(),
        search_web=search,
        fetch_page=fetch,
        index_research_sources=AsyncMock(),
        admit_source=lambda _s: "public",
        model=model,
    )

    fetch.assert_not_awaited()
    assert error == "domain_not_allowed"


@pytest.mark.asyncio
async def test_agent_search_injects_allowlist_domains(monkeypatch):
    monkeypatch.setattr(
        "app.research.research_agent.research_repo.increment_research_search_count",
        lambda *args, **kwargs: None,
    )
    search = AsyncMock(return_value=SearchResponse(results=[]))
    model = ScriptedChatModel(
        responses=[
            AIMessage(
                content="",
                tool_calls=[_tool_call("search_web", {"query": "timeout defaults"}, "1")],
            ),
            AIMessage(
                content="",
                tool_calls=[_tool_call("finish_research", {"reason": "empty"}, "2")],
            ),
            AIMessage(content="done"),
        ]
    )
    job = type("Job", (), {"id": uuid4(), "user_id": uuid4(), "manuscript_id": uuid4()})()

    await run_research_agent(
        db=type("Db", (), {"commit": lambda self: None})(),
        job=job,
        query="claim",
        evidence_index=object(),
        storage=object(),
        embeddings=object(),
        search_web=search,
        fetch_page=AsyncMock(),
        index_research_sources=AsyncMock(),
        admit_source=lambda _s: "public",
        model=model,
    )

    request = search.await_args.args[0]
    assert isinstance(request, SearchRequest)
    assert request.allowed_domains is not None
    assert "reddit.com" in request.allowed_domains
    assert "github.com" not in request.allowed_domains


@pytest.mark.asyncio
async def test_agent_search_fetch_finish_indexes_allowlisted_page(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'agent.db'}")
    prepare_test_database(engine)
    db = sessionmaker(bind=engine)()
    user = User(login_id="agent", password_hash="x", nickname="a")
    db.add(user)
    db.flush()
    manuscript = Manuscript(
        user_id=user.id,
        topic="agent",
        concept=ConceptType.TECH_DEEPDIVE,
        status=ManuscriptStatus.DRAFTING,
    )
    db.add(manuscript)
    db.commit()

    url = "https://docs.python.org/3/library/asyncio.html"
    search = AsyncMock(
        return_value=SearchResponse(
            results=[
                SearchHit(url=url, title="asyncio", snippet="timeout", provider_rank=1)
            ]
        )
    )
    fetch = AsyncMock(return_value=FetchResponse(source=_fetched(url)))
    index = AsyncMock(
        return_value=ResearchIndexResult(
            status="completed",
            indexed_source_ids=[uuid4()],
            chunk_count=1,
        )
    )
    model = ScriptedChatModel(
        responses=[
            AIMessage(
                content="",
                tool_calls=[_tool_call("search_web", {"query": "python asyncio timeout"}, "1")],
            ),
            AIMessage(
                content="",
                tool_calls=[_tool_call("fetch_page", {"url": url}, "2")],
            ),
            AIMessage(
                content="",
                tool_calls=[_tool_call("finish_research", {"reason": "indexed"}, "3")],
            ),
            AIMessage(content="done"),
        ]
    )
    job = type(
        "Job",
        (),
        {"id": uuid4(), "user_id": user.id, "manuscript_id": manuscript.id},
    )()

    error = await run_research_agent(
        db=db,
        job=job,
        query="긴 주장 " * 80,
        evidence_index=object(),
        storage=object(),
        embeddings=object(),
        search_web=search,
        fetch_page=fetch,
        index_research_sources=index,
        admit_source=lambda _s: "public",
        model=model,
    )

    assert error is None
    search.assert_awaited_once()
    fetch.assert_awaited_once()
    index.assert_awaited_once()
    request = index.await_args.args[0]
    assert isinstance(request, ResearchIndexRequest)
    assert request.sources[0].canonical_url == url
    usage = (
        db.query(ResearchUsage)
        .filter(ResearchUsage.manuscript_id == manuscript.id)
        .one()
    )
    assert usage.search_count == 1
    db.close()


@pytest.mark.asyncio
async def test_agent_rejects_fetch_over_budget(monkeypatch):
    monkeypatch.setattr(
        "app.research.research_agent.research_repo.increment_research_search_count",
        lambda *args, **kwargs: None,
    )
    url = "https://docs.python.org/3/"
    fetch = AsyncMock(return_value=FetchResponse(source=_fetched(url)))
    model = ScriptedChatModel(
        responses=[
            AIMessage(
                content="",
                tool_calls=[
                    _tool_call("fetch_page", {"url": url}, "1"),
                    _tool_call("fetch_page", {"url": url + "a"}, "2"),
                    _tool_call("fetch_page", {"url": url + "b"}, "3"),
                    _tool_call("fetch_page", {"url": url + "c"}, "4"),
                ],
            ),
            AIMessage(
                content="",
                tool_calls=[_tool_call("finish_research", {"reason": "budget"}, "5")],
            ),
            AIMessage(content="done"),
        ]
    )
    job = type("Job", (), {"id": uuid4(), "user_id": uuid4(), "manuscript_id": uuid4()})()

    await run_research_agent(
        db=type("Db", (), {"commit": lambda self: None})(),
        job=job,
        query="claim",
        evidence_index=object(),
        storage=object(),
        embeddings=object(),
        search_web=AsyncMock(),
        fetch_page=fetch,
        index_research_sources=AsyncMock(
            return_value=ResearchIndexResult(status="completed", chunk_count=1)
        ),
        admit_source=lambda _s: "public",
        model=model,
        max_fetches=3,
    )

    assert fetch.await_count == 3


def test_clip_search_query_enforces_search_request_limits():
    long_query = "word " * 60 + "x" * 50
    clipped = clip_search_query(long_query)
    assert len(clipped.split()) <= 50
    assert len(clipped) <= 400
    SearchRequest(query=clipped)
