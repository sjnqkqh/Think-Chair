from datetime import datetime, timezone
from unittest.mock import AsyncMock, Mock
from uuid import uuid4

import pytest
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
from app.research.web_research import expand_evidence_via_web_search
from tests.db_setup import prepare_test_database

pytestmark = pytest.mark.unit


def _summarize_stub(_prompt: str) -> str:
    return "github actions job timeout default"


@pytest.mark.asyncio
async def test_expand_evidence_via_web_search_indexes_fetched_hits(monkeypatch):
    search = AsyncMock(
        return_value=SearchResponse(
            results=[
                SearchHit(
                    url="https://docs.example/timeout",
                    title="Timeout",
                    snippet="360분",
                    provider_rank=1,
                )
            ]
        )
    )
    fetched = FetchedSource(
        requested_url="https://docs.example/timeout",
        canonical_url="https://docs.example/timeout",
        title="Timeout",
        publisher="Example",
        published_at="2026-01-01",
        text="기본 job timeout은 360분이다. " * 20,
        sections=[],
        media_type="text/html",
        fetched_at=datetime.now(timezone.utc),
        content_hash="hash",
        source_key="key",
    )
    fetch = AsyncMock(return_value=FetchResponse(source=fetched))
    index = AsyncMock(
        return_value=ResearchIndexResult(
            status="completed",
            indexed_source_ids=[uuid4()],
            chunk_count=1,
        )
    )
    job = type(
        "Job",
        (),
        {
            "id": uuid4(),
            "user_id": uuid4(),
            "manuscript_id": uuid4(),
        },
    )()
    monkeypatch.setattr(
        "app.research.web_research.research_repo.increment_research_search_count",
        lambda *args, **kwargs: None,
    )

    class _Db:
        def commit(self):
            return None

    await expand_evidence_via_web_search(
        db=_Db(),
        job=job,
        query="timeout 기본값",
        evidence_index=object(),
        storage=object(),
        embeddings=object(),
        search_web=search,
        fetch_page=fetch,
        index_research_sources=index,
        admit_source=lambda _source: "public",
        summarize_query=_summarize_stub,
        max_fetches=2,
    )

    search.assert_awaited_once()
    fetch.assert_awaited_once()
    index.assert_awaited_once()
    request = index.await_args.args[0]
    assert isinstance(request, ResearchIndexRequest)
    assert request.sources[0].canonical_url == "https://docs.example/timeout"


@pytest.mark.asyncio
async def test_expand_evidence_increments_manuscript_search_count(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'web.db'}")
    prepare_test_database(engine)
    db = sessionmaker(bind=engine)()
    user = User(login_id="search-count", password_hash="x", nickname="s")
    db.add(user)
    db.flush()
    manuscript = Manuscript(
        user_id=user.id,
        topic="search",
        concept=ConceptType.TECH_DEEPDIVE,
        status=ManuscriptStatus.DRAFTING,
    )
    db.add(manuscript)
    db.commit()

    search = AsyncMock(return_value=SearchResponse(results=[]))
    job = type(
        "Job",
        (),
        {"id": uuid4(), "user_id": user.id, "manuscript_id": manuscript.id},
    )()

    error = await expand_evidence_via_web_search(
        db=db,
        job=job,
        query="일반론",
        evidence_index=object(),
        storage=object(),
        embeddings=object(),
        search_web=search,
        fetch_page=AsyncMock(),
        index_research_sources=AsyncMock(),
        admit_source=lambda _source: "public",
        summarize_query=_summarize_stub,
    )

    assert error == "search_empty"
    usage = (
        db.query(ResearchUsage)
        .filter(ResearchUsage.manuscript_id == manuscript.id)
        .one()
    )
    assert usage.search_count == 1
    db.close()


@pytest.mark.asyncio
async def test_expand_evidence_calls_llm_to_summarize_english_search_keywords(
    monkeypatch,
):
    """긴 claim을 Brave에 넣기 전에 LLM으로 영어 키워드로 변환하는지 검증한다."""
    search = AsyncMock(return_value=SearchResponse(results=[]))
    summarize_query = Mock(
        return_value="AI model usability task routing Opus Gemini Flash"
    )
    job = type(
        "Job",
        (),
        {"id": uuid4(), "user_id": uuid4(), "manuscript_id": uuid4()},
    )()
    monkeypatch.setattr(
        "app.research.web_research.research_repo.increment_research_search_count",
        lambda *args, **kwargs: None,
    )

    class _Db:
        def commit(self):
            return None

    long_claim = (
        "사용자의 요구사항을 분석하고, 계획을 수립하며, 이를 구현할 수 있는가의 "
        "문제입니다. 사용성 허들은 사용자마다, 또한 작업 마다 다릅니다. 앞서 "
        "언급한 두 모델 모두 가벼운 파이썬 스크립트를 코딩하기엔 충분하지만, "
        "Gemini 3.5 flash는 5,000 줄 가량의 PR을 한번의 작업 지시로 수행하지는 "
        "못합니다. 또한 두 모델 모두 코딩에는 익숙하지만, word 문서를 "
        "만들어달라고 요구하면 많은 난항에 부딪힙니다. "
        "또한 사용성 허들은 모든 모델에 일률적으로 적용되지 않습니다. 이제 AI에 "
        "익숙한 유저들은 모델들에 일괄적인 작업을 부여하는 방식보단 모델의 "
        "크기와 성능에 따라 적합한 일을 배분합니다. 예컨데 맞춤법 교정처럼 "
        "상대적으로 적은 컨텍스트를 차지하는 작업의 경우 경량 모델을, 수 만 "
        "줄의 코드 베이스에서 PR 생성을 Opus를 사용하는 식이고 이 작업들이 "
        "성공적으로 완수되길 바라는 심리가 사용성 허들입니다."
    )
    assert len(long_claim) > 400
    assert len(long_claim.split()) > 50

    error = await expand_evidence_via_web_search(
        db=_Db(),
        job=job,
        query=long_claim,
        evidence_index=object(),
        storage=object(),
        embeddings=object(),
        search_web=search,
        fetch_page=AsyncMock(),
        index_research_sources=AsyncMock(),
        admit_source=lambda _source: "public",
        summarize_query=summarize_query,
    )

    assert error == "search_empty"
    summarize_query.assert_called_once()
    prompt = summarize_query.call_args.args[0]
    assert long_claim in prompt
    search.assert_awaited_once()
    request = search.await_args.args[0]
    assert isinstance(request, SearchRequest)
    assert request.query == "AI model usability task routing Opus Gemini Flash"
    assert len(request.query) <= 400
    assert len(request.query.split()) <= 50
