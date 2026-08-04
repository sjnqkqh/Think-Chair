"""실제 DB 계정으로 ‘일반론 주장 → 근거 보강 조사’ 한 바퀴를 검증하는 live E2E.

제품 의도: 사용자가 “확인해 주세요”를 요청해서가 아니라,
대화 중 일반론·모범 사례·대략적 수치 주장을 했을 때 에이전트가 조사를 걸고
더 구체적인 근거(벤치마크·설정 사례·공식 가이드)를 모아 주장을 보강한다.

실패는 버그 리포트라기보다 트리거(`detect_evidence_need`)·검색 품질 신호다.
기본 테스트에서는 건너뛴다. 필요할 때마다:

    RUN_LIVE_RESEARCH_E2E=1 \\
      LIVE_RESEARCH_LOGIN_ID=admin \\
      uv run pytest tests/e2e/test_live_research_conversation.py -v -s
"""

from __future__ import annotations

import asyncio
import json
import os
import uuid
from dataclasses import dataclass
from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import SessionLocal, get_database_session
from app.core.security import create_jwt
from app.main import app as fastapi_app
from app.models.manuscript import Manuscript
from app.models.research import (
    ResearchJob,
    ResearchJobSource,
    ResearchJobStatus,
    ResearchSource,
    ResearchSourceStatus,
)
from app.models.user import User
from app.repositories import research_repo
from app.research.indexing import create_research_evidence_index

TERMINAL_STATUSES = {
    ResearchJobStatus.COMPLETED.value,
    ResearchJobStatus.PARTIAL.value,
    ResearchJobStatus.FAILED.value,
    ResearchJobStatus.CANCELLED.value,
}


@dataclass(frozen=True)
class LiveResearchCase:
    """일반론 주장 한 건.

    claim: 사용자가 대화에 던지는 일반론/주장 문장(확인 요청이 아님).
    evidence_hope: 조사가 모아 주장을 구체화했으면 하는 근거 방향(문서용).
    """

    case_id: str
    topic: str
    claim: str
    evidence_hope: str


LIVE_RESEARCH_CASES = [
    LiveResearchCase(
        case_id="autoscaling_cpu_memory",
        topic="오토스케일링 지표",
        claim=(
            "오토 스케일링 시, 보통 CPU 점유율이나 Memory 점유율을 기준으로 "
            "서버 증감을 수행합니다."
        ),
        evidence_hope=(
            "클라우드/쿠버네티스 오토스케일링에서 CPU·메모리 임계값 모범 사례와 "
            "실제 증감 설정 사례"
        ),
    ),
    LiveResearchCase(
        case_id="four_bit_quantization",
        topic="4비트 양자화",
        claim=(
            "일반적으로 4비트 양자화까지는 성능이 크게 떨어지지 않습니다."
        ),
        evidence_hope=(
            "특정 LLM 기준 4비트 양자화 시 벤치마크 성능 변화와 메모리 점유량 감소 사례"
        ),
    ),
    LiveResearchCase(
        case_id="redis_cache_hit_rate",
        topic="캐시 hit rate",
        claim=(
            "보통 Redis 캐시 hit rate가 90% 이상이면 캐시 계층이 잘 동작한다고 봅니다."
        ),
        evidence_hope="캐시 hit rate 목표치·모니터링 기준에 대한 실무/공식 가이드",
    ),
    LiveResearchCase(
        case_id="connection_pool_size",
        topic="DB 커넥션 풀",
        claim=(
            "웹 서비스에서는 보통 워커당 DB 커넥션 풀 크기를 작게 유지하는 편이 "
            "안전합니다."
        ),
        evidence_hope="워커 수·풀 크기 산정 모범 사례와 과도한 풀로 인한 장애 사례",
    ),
    LiveResearchCase(
        case_id="rag_chunk_size",
        topic="RAG 청크 크기",
        claim=(
            "RAG에서는 청크를 대략 500토큰 전후로 나누는 게 일반적입니다."
        ),
        evidence_hope="임베딩/검색 품질 관점의 청크 크기·오버랩 권장 수치와 실험 결과",
    ),
]

pytestmark = [
    pytest.mark.e2e,
    pytest.mark.live_web,
    pytest.mark.skipif(
        os.getenv("RUN_LIVE_RESEARCH_E2E") != "1",
        reason="RUN_LIVE_RESEARCH_E2E=1일 때만 실제 계정·검색·인덱싱 E2E를 돌린다.",
    ),
    pytest.mark.skipif(
        not settings.BRAVE_SEARCH_API_KEY,
        reason="BRAVE_SEARCH_API_KEY가 필요하다.",
    ),
    pytest.mark.skipif(
        not settings.OPENAI_API_KEY,
        reason="OPENAI_API_KEY가 필요하다(임베딩·비교 생성).",
    ),
]


def _parse_sse_events(body: str) -> list[tuple[str, dict]]:
    events: list[tuple[str, dict]] = []
    for block in body.strip().split("\n\n"):
        if not block.strip():
            continue
        event_name = "message"
        data_line = None
        for line in block.split("\n"):
            if line.startswith("event:"):
                event_name = line.split(":", 1)[1].strip()
            elif line.startswith("data:"):
                data_line = line.split(":", 1)[1].strip()
        if data_line is None:
            continue
        payload = json.loads(data_line) if data_line else {}
        events.append((event_name, payload))
    return events


def _resolve_stored_user(db: Session) -> User:
    login_id = os.getenv("LIVE_RESEARCH_LOGIN_ID", "admin")
    user = db.query(User).filter(User.login_id == login_id).one_or_none()
    if user is None:
        raise AssertionError(
            f"DB에 login_id={login_id!r} 사용자가 없다. "
            "LIVE_RESEARCH_LOGIN_ID로 실제 계정을 지정하라."
        )
    return user


async def _authenticate(
    client: AsyncClient,
    *,
    user_id: uuid.UUID,
    login_id: str,
) -> None:
    password = os.getenv("LIVE_RESEARCH_PASSWORD")
    if password:
        login_res = await client.post(
            "/api/auth/login",
            json={"login_id": login_id, "password": password},
        )
        assert login_res.status_code == 200, login_res.text
        return
    # 로컬 live 검증용: DB에 있는 실 계정으로 JWT를 발급해 쿠키에 넣는다.
    client.cookies.set("access_token", create_jwt(str(user_id)))


async def _poll_research_job(
    client: AsyncClient,
    *,
    job_id: uuid.UUID,
    manuscript_id: str,
    timeout_seconds: float = 240,
) -> dict:
    deadline = asyncio.get_running_loop().time() + timeout_seconds
    while True:
        status_res = await client.get(
            f"/api/research/jobs/{job_id}",
            params={"manuscript_id": manuscript_id},
        )
        assert status_res.status_code == 200, status_res.text
        body = status_res.json()
        if body["status"] in TERMINAL_STATUSES:
            return body
        if asyncio.get_running_loop().time() >= deadline:
            raise AssertionError(
                f"조사 job이 {timeout_seconds:.0f}초 내 끝나지 않았다: {body}"
            )
        await asyncio.sleep(2)


async def _soft_delete_manuscript(client: AsyncClient, manuscript_id: str) -> None:
    delete_res = await client.delete(f"/api/manuscripts/{manuscript_id}")
    assert delete_res.status_code == 204, delete_res.text
    db = SessionLocal()
    try:
        manuscript = db.get(Manuscript, uuid.UUID(manuscript_id))
        assert manuscript is not None
        assert manuscript.is_deleted is True
    finally:
        db.close()


async def _run_research_conversation_case(
    client: AsyncClient,
    *,
    user_id: uuid.UUID,
    case: LiveResearchCase,
) -> None:
    manuscript_id: str | None = None
    try:
        create_res = await client.post(
            "/api/manuscripts",
            json={
                "topic": f"live-research-e2e-{case.case_id}-{uuid.uuid4().hex[:8]}",
                "concept": "딥다이브",
            },
        )
        assert create_res.status_code == 201, create_res.text
        manuscript_id = create_res.json()["id"]

        message_res = await client.post(
            f"/api/chat/{manuscript_id}/message",
            data={"content": case.claim},
        )
        assert message_res.status_code == 200, message_res.text
        events = _parse_sse_events(message_res.text)
        research_events = [
            payload for name, payload in events if name == "research_required"
        ]
        assert research_events, (
            f"[{case.case_id}] 일반론 주장인데 research_required가 없다 "
            f"(트리거 미검출). claim={case.claim!r} "
            f"evidence_hope={case.evidence_hope!r} "
            f"events={[name for name, _ in events]}"
        )
        research_payload = research_events[0]
        assert research_payload["manuscript_id"] == manuscript_id
        assert research_payload["message_id"]
        assert research_payload["claim_or_query"]

        job_res = await client.post(
            "/api/research/jobs",
            json={
                "manuscript_id": manuscript_id,
                "message_id": research_payload["message_id"],
                "claim_or_query": research_payload["claim_or_query"],
            },
        )
        assert job_res.status_code == 202, job_res.text
        job_body = job_res.json()
        job_id = uuid.UUID(job_body["id"])
        assert job_body["created"] is True

        final_status = await _poll_research_job(
            client,
            job_id=job_id,
            manuscript_id=manuscript_id,
        )
        assert final_status["status"] in {
            ResearchJobStatus.COMPLETED.value,
            ResearchJobStatus.PARTIAL.value,
        }, f"[{case.case_id}] {final_status}"
        assert not final_status.get("terminal_error"), f"[{case.case_id}] {final_status}"
        assert final_status["evidence_ready"] is True, f"[{case.case_id}] {final_status}"

        db = SessionLocal()
        try:
            job = db.get(ResearchJob, job_id)
            assert job is not None
            assert job.user_id == user_id

            links = (
                db.query(ResearchJobSource)
                .filter(ResearchJobSource.research_job_id == job_id)
                .all()
            )
            assert links, f"[{case.case_id}] research_job_sources에 연결된 원문이 없다"

            sources = (
                db.query(ResearchSource)
                .filter(ResearchSource.id.in_([link.source_id for link in links]))
                .all()
            )
            assert sources
            indexed = [
                source
                for source in sources
                if source.status == ResearchSourceStatus.INDEXED
            ]
            assert indexed, (
                f"[{case.case_id}] INDEXED 원문이 없다: {[s.status for s in sources]}"
            )

            evidence_index = create_research_evidence_index()
            total_chunks = 0
            for source in indexed:
                stored = evidence_index.collections["public"].get(
                    where={"source_id": str(source.id)},
                    include=[],
                )
                total_chunks += len(stored.get("ids") or [])
            assert total_chunks >= 1, f"[{case.case_id}] Chroma에 청크가 하나도 없다"
        finally:
            db.close()
    finally:
        if manuscript_id is not None:
            await _soft_delete_manuscript(client, manuscript_id)


@pytest.fixture
async def live_research_client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """실 DB·실 lifespan ChatService로 ASGI 클라이언트를 연다.

    1) 기존 chroma_db 청크 때문에 웹 검색이 생략되지 않도록 케이스마다 빈 Chroma를 쓴다.
    2) 이전 live 실행으로 DB에 남은 INDEXED 원문은 벡터를 건너뛰므로,
       이 테스트의 빈 Chroma에 다시 심도록 재인덱싱을 강제한다.
    """
    # conftest autouse가 메모리 DB로 덮어쓰므로 실 DB로 되돌린다.
    fastapi_app.dependency_overrides.pop(get_database_session, None)
    monkeypatch.setattr(settings, "CHROMA_ROOT", tmp_path / "chroma_live_research")

    original_find = research_repo.find_source_by_url

    def find_source_and_force_reindex(*args, **kwargs):
        source = original_find(*args, **kwargs)
        if source is not None and source.status == ResearchSourceStatus.INDEXED:
            source.status = ResearchSourceStatus.FAILED
        return source

    monkeypatch.setattr(
        "app.research.indexing.research_repo.find_source_by_url",
        find_source_and_force_reindex,
    )

    async with fastapi_app.router.lifespan_context(fastapi_app):
        transport = ASGITransport(app=fastapi_app)
        async with AsyncClient(
            transport=transport,
            base_url="http://testserver",
            timeout=120.0,
        ) as client:
            yield client


@pytest.mark.parametrize(
    "case",
    LIVE_RESEARCH_CASES,
    ids=[case.case_id for case in LIVE_RESEARCH_CASES],
)
async def test_stored_user_general_claim_triggers_evidence_research(
    live_research_client: AsyncClient,
    case: LiveResearchCase,
):
    """일반론 주장 → 조사 job → 웹 검색·수집·청킹으로 근거를 보강하는지 검증한다."""
    assert len(LIVE_RESEARCH_CASES) >= 5

    db = SessionLocal()
    try:
        user = _resolve_stored_user(db)
        user_id = user.id
        login_id = user.login_id
    finally:
        db.close()

    await _authenticate(
        live_research_client,
        user_id=user_id,
        login_id=login_id,
    )
    await _run_research_conversation_case(
        live_research_client,
        user_id=user_id,
        case=case,
    )
