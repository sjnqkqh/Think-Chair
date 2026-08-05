#!/usr/bin/env python3
"""로컬 서버에서 실제 대화를 재생해, 서로 다른 LLM 엔드포인트/모델 프로필의
답변·문서 평가를 비교하는 재현 스크립트다. pytest가 아니라 직접 실행한다.

사전 준비:
    - `--host` / `--port`에 지정한 서버가 떠 있어야 한다
      (기본 `127.0.0.1:8001`).
    - 로그인 가능한 계정이 있어야 한다 (REPRO_LOGIN_ID / REPRO_PASSWORD 또는
      --login-id / --password).
    - --manuscript-id로 넘긴 원고(기본값은 사용자 메시지가 있는 기존 원고)를
      그 계정이 소유하고 있어야 한다. 이 원고의 사용자 발화를 그대로 재생한다.

사용 예:
    # 서버 기본(DeepSeek)만 — 워크트리 uvicorn(127.0.0.1:8001) 기준
    uv run python scripts/reproduce_multi_model_run.py \\
        --host 127.0.0.1 --port 8001 \\
        --login-id YOUR_ID --password YOUR_PASSWORD

    # DeepSeek 기본 + OpenAI gpt-5.6-luna 비교
    # luna의 OpenAI 호환 base는 https://api.openai.com/v1 이다.
    uv run python scripts/reproduce_multi_model_run.py \\
        --host 127.0.0.1 --port 8001 \\
        --login-id YOUR_ID --password YOUR_PASSWORD \\
        --profile luna \\
        --model gpt-5.6-luna \\
        --api-base https://api.openai.com/v1 \\
        --api-key "$OPENAI_API_KEY"

    # 여러 벤더를 같은 순서로 반복 (--profile / --model / --api-base / --api-key)
    uv run python scripts/reproduce_multi_model_run.py \\
        --host 127.0.0.1 --port 8001 \\
        --profile luna --model gpt-5.6-luna \\
        --api-base https://api.openai.com/v1 --api-key "$OPENAI_API_KEY" \\
        --profile deepseek-alt --model deepseek-chat \\
        --api-base https://api.deepseek.com --api-key "$DEEPSEEK_API_KEY"

프로필:
    "default" 프로필은 항상 맨 앞에 포함되며 model/api_base/api_key를 보내지 않아
    서버 기본값(DEEPSEEK_*)을 그대로 쓴다.

    추가 프로필은 --profile NAME 과 짝을 이루는 --model / --api-base / --api-key 로
    지정한다 (인덱스 순서로 매칭). 벤더가 바뀌면 엔드포인트와 API 키를 함께 넘긴다.

    gpt-5.6-luna 기준:
      --model gpt-5.6-luna
      --api-base https://api.openai.com/v1
      --api-key  (OpenAI API 키; 프로젝트 .env 의 OPENAI_API_KEY 와 동일 계열)

    단축 표기 --profile NAME:MODEL:API_BASE 도 허용하며, 같은 인덱스의
    --model/--api-base/--api-key 가 있으면 CLI 값이 우선한다.
    CLI에 없는 값은 {NAME}_API_BASE / {NAME}_API_KEY 환경변수로 보완한다.
"""

from __future__ import annotations

import argparse
import dataclasses
import datetime
import json
import os
import sys
import time
from pathlib import Path

import httpx

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8001
DEFAULT_MANUSCRIPT_ID = "fef1b1e5-ddcd-426d-8808-3f8746d70e96"
ARTIFACTS_DIR = Path(__file__).resolve().parent.parent / "artifacts" / "multi_model_runs"
TERMINAL_RESEARCH_STATUSES = {"completed", "partial", "failed", "cancelled"}


@dataclasses.dataclass(frozen=True)
class Profile:
    name: str
    model: str | None = None
    api_base: str | None = None
    api_key: str | None = None


@dataclasses.dataclass
class SourceConversation:
    manuscript_id: str
    topic: str
    concept: str
    audience_level: str | None
    user_messages: list[str]


@dataclasses.dataclass
class TurnRecord:
    user_content: str
    assistant_reply: str = ""
    research: bool = False
    document_generation: bool = False
    error: str | None = None


@dataclasses.dataclass
class ProfileRun:
    profile: Profile
    manuscript_id: str | None = None
    turns: list[TurnRecord] = dataclasses.field(default_factory=list)
    evaluations: list[dict] = dataclasses.field(default_factory=list)
    final_message_count: int | None = None
    fatal_error: str | None = None


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--host",
        default=DEFAULT_HOST,
        help=f"대상 서버 호스트 주소 (기본: {DEFAULT_HOST})",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=DEFAULT_PORT,
        help=f"대상 서버 포트 (기본: {DEFAULT_PORT})",
    )
    parser.add_argument(
        "--manuscript-id",
        default=DEFAULT_MANUSCRIPT_ID,
        help="재생할 원본 원고 id (사용자 메시지를 그대로 재현한다)",
    )
    parser.add_argument(
        "--login-id",
        default=os.environ.get("REPRO_LOGIN_ID"),
        help="로그인 id (기본값: REPRO_LOGIN_ID 환경변수)",
    )
    parser.add_argument(
        "--password",
        default=os.environ.get("REPRO_PASSWORD"),
        help="로그인 비밀번호 (기본값: REPRO_PASSWORD 환경변수)",
    )
    parser.add_argument(
        "--profile",
        dest="profile_specs",
        action="append",
        default=[],
        metavar="NAME[:MODEL[:API_BASE]]",
        help=(
            "비교할 추가 프로필 이름(여러 번 지정 가능). "
            "같은 순서의 --model / --api-base / --api-key 와 짝을 이룬다. "
            "단축: NAME:MODEL:API_BASE. default(서버 DeepSeek)는 항상 포함."
        ),
    )
    parser.add_argument(
        "--model",
        dest="models",
        action="append",
        default=[],
        metavar="MODEL",
        help="프로필별 provider 모델 id (--profile 과 같은 순서로 반복)",
    )
    parser.add_argument(
        "--api-base",
        dest="api_bases",
        action="append",
        default=[],
        metavar="URL",
        help=(
            "프로필별 OpenAI 호환 API base URL (--profile 과 같은 순서로 반복). "
            "gpt-5.6-luna 는 https://api.openai.com/v1"
        ),
    )
    parser.add_argument(
        "--api-key",
        dest="api_keys",
        action="append",
        default=[],
        metavar="KEY",
        help="프로필별 API 키 (--profile 과 같은 순서로 반복). 벤더가 바뀌면 함께 지정",
    )
    parser.add_argument(
        "--request-timeout",
        type=float,
        default=120.0,
        help="HTTP 요청(스트리밍 답변 포함) 타임아웃(초). 기본 120",
    )
    parser.add_argument(
        "--research-timeout",
        type=float,
        default=240.0,
        help="조사 job 완료 대기 타임아웃(초). 기본 240",
    )
    parser.add_argument(
        "--evaluation-timeout",
        type=float,
        default=180.0,
        help="문서 생성 후 평가 결과 대기 타임아웃(초). 기본 180",
    )
    parser.add_argument(
        "--poll-interval",
        type=float,
        default=2.0,
        help="조사 job/평가 폴링 간격(초). 기본 2",
    )
    parser.add_argument(
        "--output",
        default=None,
        help="결과 markdown 경로 (기본: artifacts/multi_model_runs/<timestamp>.md)",
    )
    return parser.parse_args()


def server_base_url(args: argparse.Namespace) -> str:
    return f"http://{args.host}:{args.port}"


def _nth(values: list[str], index: int) -> str | None:
    if index >= len(values):
        return None
    value = values[index].strip()
    return value or None


def parse_profile_spec(
    spec: str,
    *,
    model: str | None = None,
    api_base: str | None = None,
    api_key: str | None = None,
) -> Profile:
    parts = spec.split(":", 2)
    name = parts[0].strip()
    if not name:
        raise SystemExit(f"--profile 형식이 잘못됐다(이름 없음): {spec!r}")

    shorthand_model = parts[1].strip() if len(parts) > 1 and parts[1].strip() else None
    shorthand_base = parts[2].strip() if len(parts) > 2 and parts[2].strip() else None

    env_prefix = name.upper().replace("-", "_")
    resolved_model = model or shorthand_model
    resolved_base = (
        api_base
        or shorthand_base
        or os.environ.get(f"{env_prefix}_API_BASE")
        or None
    )
    resolved_key = api_key or os.environ.get(f"{env_prefix}_API_KEY") or None

    if (resolved_model or resolved_base) and not resolved_key:
        raise SystemExit(
            f"프로필 {name!r}: 모델/엔드포인트를 바꿨으면 --api-key 도 필요하다 "
            f"(또는 {env_prefix}_API_KEY 환경변수)."
        )

    return Profile(
        name=name,
        model=resolved_model,
        api_base=resolved_base,
        api_key=resolved_key,
    )


def build_profiles(args: argparse.Namespace) -> list[Profile]:
    specs = list(args.profile_specs)
    models = list(args.models)
    api_bases = list(args.api_bases)
    api_keys = list(args.api_keys)

    # --profile 없이 --model/--api-base/--api-key 만 준 경우 단일 실험 프로필로 취급
    if not specs and (models or api_bases or api_keys):
        specs = ["experiment"]

    for label, values in (
        ("--model", models),
        ("--api-base", api_bases),
        ("--api-key", api_keys),
    ):
        if values and len(values) != len(specs):
            raise SystemExit(
                f"{label} 개수({len(values)})가 --profile 개수({len(specs)})와 다르다."
            )

    profiles = [Profile(name="default")]
    for index, spec in enumerate(specs):
        profiles.append(
            parse_profile_spec(
                spec,
                model=_nth(models, index),
                api_base=_nth(api_bases, index),
                api_key=_nth(api_keys, index),
            )
        )
    return profiles


def parse_sse_events(body: str) -> list[tuple[str, dict]]:
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


def login(client: httpx.Client, login_id: str | None, password: str | None) -> None:
    if not login_id or not password:
        raise SystemExit(
            "로그인 정보가 없다. --login-id/--password 또는 "
            "REPRO_LOGIN_ID/REPRO_PASSWORD 환경변수를 설정해라."
        )
    response = client.post(
        "/api/auth/login", json={"login_id": login_id, "password": password}
    )
    response.raise_for_status()


def fetch_source_conversation(client: httpx.Client, manuscript_id: str) -> SourceConversation:
    manuscript_res = client.get(f"/api/manuscripts/{manuscript_id}")
    manuscript_res.raise_for_status()
    manuscript = manuscript_res.json()

    messages_res = client.get(f"/api/chat/{manuscript_id}/messages")
    messages_res.raise_for_status()
    user_messages = [m["content"] for m in messages_res.json() if m["role"] == "user"]

    return SourceConversation(
        manuscript_id=manuscript_id,
        topic=manuscript["topic"],
        concept=manuscript["concept"],
        audience_level=manuscript.get("audience_level"),
        user_messages=user_messages,
    )


def send_chat_message(
    client: httpx.Client, manuscript_id: str, content: str, profile: Profile
) -> list[tuple[str, dict]]:
    data: dict[str, str] = {"content": content}
    if profile.model:
        data["model"] = profile.model
    if profile.api_base:
        data["api_base"] = profile.api_base
    if profile.api_key:
        data["api_key"] = profile.api_key
    response = client.post(f"/api/chat/{manuscript_id}/message", data=data)
    response.raise_for_status()
    return parse_sse_events(response.text)


def create_research_job(
    client: httpx.Client, manuscript_id: str, message_id: str, claim_or_query: str
) -> dict:
    response = client.post(
        "/api/research/jobs",
        json={
            "manuscript_id": manuscript_id,
            "message_id": message_id,
            "claim_or_query": claim_or_query,
        },
    )
    response.raise_for_status()
    return response.json()


def wait_for_research_job(
    client: httpx.Client,
    job_id: str,
    manuscript_id: str,
    *,
    timeout: float,
    interval: float,
) -> dict:
    deadline = time.monotonic() + timeout
    while True:
        response = client.get(
            f"/api/research/jobs/{job_id}", params={"manuscript_id": manuscript_id}
        )
        response.raise_for_status()
        body = response.json()
        if body.get("status") in TERMINAL_RESEARCH_STATUSES:
            return body
        if time.monotonic() >= deadline:
            raise TimeoutError(f"조사 job이 {timeout:.0f}초 내 끝나지 않았다: {body}")
        time.sleep(interval)


def continue_research(
    client: httpx.Client,
    job_id: str,
    manuscript_id: str,
    message_id: str,
    profile: Profile,
) -> list[tuple[str, dict]]:
    body = {
        "manuscript_id": manuscript_id,
        "message_id": message_id,
        "model": profile.model,
        "api_base": profile.api_base,
        "api_key": profile.api_key,
    }
    response = client.post(f"/api/research/jobs/{job_id}/continue", json=body)
    response.raise_for_status()
    return parse_sse_events(response.text)


def wait_for_evaluations(
    client: httpx.Client,
    manuscript_id: str,
    *,
    min_count: int,
    timeout: float,
    interval: float,
) -> list[dict]:
    deadline = time.monotonic() + timeout
    while True:
        response = client.get(f"/api/manuscripts/{manuscript_id}/evaluations")
        response.raise_for_status()
        evaluations = response.json()
        if len(evaluations) > min_count:
            return evaluations
        if time.monotonic() >= deadline:
            print(
                f"경고: {timeout:.0f}초 내 문서 평가 결과가 나타나지 않았다.",
                file=sys.stderr,
            )
            return evaluations
        time.sleep(interval)


def run_profile(
    client: httpx.Client,
    profile: Profile,
    source: SourceConversation,
    args: argparse.Namespace,
) -> ProfileRun:
    run = ProfileRun(profile=profile)
    try:
        create_res = client.post(
            "/api/manuscripts",
            json={
                "topic": source.topic,
                "concept": source.concept,
                "audience_level": source.audience_level,
            },
        )
        create_res.raise_for_status()
        manuscript_id = create_res.json()["id"]
        run.manuscript_id = manuscript_id

        document_generation_seen = False
        for user_content in source.user_messages:
            turn = TurnRecord(user_content=user_content)
            run.turns.append(turn)

            events = send_chat_message(client, manuscript_id, user_content, profile)

            error_event = next((p for n, p in events if n == "error"), None)
            if error_event:
                turn.error = error_event.get("message", "알 수 없는 오류")
                continue

            research_event = next(
                (p for n, p in events if n == "research_required"), None
            )
            if research_event:
                turn.research = True
                job = create_research_job(
                    client,
                    manuscript_id,
                    research_event["message_id"],
                    research_event["claim_or_query"],
                )
                job_status = wait_for_research_job(
                    client,
                    job["id"],
                    manuscript_id,
                    timeout=args.research_timeout,
                    interval=args.poll_interval,
                )
                if job_status.get("terminal_error"):
                    turn.error = f"조사 실패: {job_status['terminal_error']}"
                    continue
                events = continue_research(
                    client,
                    job["id"],
                    manuscript_id,
                    research_event["message_id"],
                    profile,
                )
                continue_error = next((p for n, p in events if n == "error"), None)
                if continue_error:
                    turn.error = continue_error.get("message", "알 수 없는 오류")
                    continue

            done_event = next((p for n, p in events if n == "done"), {})
            if done_event.get("document_generation"):
                turn.document_generation = True
                document_generation_seen = True

            turn.assistant_reply = "".join(
                p.get("content", "") for n, p in events if n == "chunk"
            )

        if document_generation_seen:
            run.evaluations = wait_for_evaluations(
                client,
                manuscript_id,
                min_count=0,
                timeout=args.evaluation_timeout,
                interval=args.poll_interval,
            )

        final_messages_res = client.get(f"/api/chat/{manuscript_id}/messages")
        final_messages_res.raise_for_status()
        run.final_message_count = len(final_messages_res.json())
    except (httpx.HTTPStatusError, httpx.RequestError, TimeoutError) as exc:
        run.fatal_error = str(exc)
    return run


def render_markdown(
    source: SourceConversation, runs: list[ProfileRun], generated_at: str
) -> str:
    lines = [
        f"# 멀티 모델 비교 재현 결과 ({generated_at})",
        "",
        f"- 원본 원고: `{source.manuscript_id}`",
        f"- 주제: {source.topic} / 컨셉: {source.concept} / "
        f"독자 수준: {source.audience_level or '-'}",
        f"- 재현할 사용자 메시지 수: {len(source.user_messages)}",
        "",
    ]

    for run in runs:
        profile = run.profile
        lines.append(f"## 프로필: {profile.name}")
        lines.append("")
        lines.append(f"- model: `{profile.model or '(서버 기본값)'}`")
        lines.append(f"- api_base: `{profile.api_base or '(서버 기본값)'}`")
        lines.append(f"- api_key: {'설정됨' if profile.api_key else '(서버 기본값)'}")
        lines.append(f"- 새 원고 id: `{run.manuscript_id or '(생성 실패)'}`")
        if run.final_message_count is not None:
            lines.append(f"- 최종 채팅 메시지 수: {run.final_message_count}")
        lines.append("")

        if run.fatal_error:
            lines.append(f"**실패:** {run.fatal_error}")
            lines.append("")
            continue

        lines.append("### 대화")
        lines.append("")
        for i, turn in enumerate(run.turns, start=1):
            lines.append(f"**{i}. 사용자:** {turn.user_content}")
            lines.append("")
            if turn.error:
                lines.append(f"> 오류: {turn.error}")
            else:
                tags = []
                if turn.research:
                    tags.append("조사 수행")
                if turn.document_generation:
                    tags.append("문서 생성 시작")
                tag_suffix = f" _({', '.join(tags)})_" if tags else ""
                lines.append(
                    f"**어시스턴트{tag_suffix}:** {turn.assistant_reply or '(응답 없음)'}"
                )
            lines.append("")

        lines.append("### 문서 평가")
        lines.append("")
        if not run.evaluations:
            lines.append("_평가 결과 없음 (문서 생성이 없었거나 완료 전 타임아웃)_")
        else:
            for evaluation in run.evaluations:
                lines.append(f"- version `{evaluation.get('version_id')}`")
                lines.append(f"  - score: {evaluation.get('score')}")
                lines.append(f"  - verdict: {evaluation.get('verdict')}")
                lines.append(f"  - reason: {evaluation.get('reason')}")
                lines.append(f"  - improvements: {evaluation.get('improvements')}")
                lines.append(
                    "  - has_unnecessary_header/footer: "
                    f"{evaluation.get('has_unnecessary_header')}/"
                    f"{evaluation.get('has_unnecessary_footer')}"
                )
                lines.append(f"  - checklist_id: {evaluation.get('checklist_id')}")
                raw_output = (evaluation.get("raw_output") or "").strip()
                if raw_output:
                    lines.append("  - raw_output:")
                    lines.append("    ```")
                    for raw_line in raw_output.splitlines():
                        lines.append(f"    {raw_line}")
                    lines.append("    ```")
        lines.append("")

    return "\n".join(lines)


def main() -> None:
    args = parse_args()
    profiles = build_profiles(args)

    with httpx.Client(
        base_url=server_base_url(args), timeout=args.request_timeout
    ) as client:
        login(client, args.login_id, args.password)
        source = fetch_source_conversation(client, args.manuscript_id)
        if not source.user_messages:
            raise SystemExit(
                f"원고 {args.manuscript_id}에 재생할 사용자 메시지가 없다."
            )

        runs = [run_profile(client, profile, source, args) for profile in profiles]

    output_path = (
        Path(args.output)
        if args.output
        else ARTIFACTS_DIR / f"{datetime.datetime.now():%Y%m%d-%H%M%S}.md"
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    markdown = render_markdown(
        source, runs, datetime.datetime.now().isoformat(timespec="seconds")
    )
    output_path.write_text(markdown, encoding="utf-8")
    print(f"결과를 저장했다: {output_path}")


if __name__ == "__main__":
    main()
