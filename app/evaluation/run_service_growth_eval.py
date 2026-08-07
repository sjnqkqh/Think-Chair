"""서비스 성장 관측용 절대 점수 평가 실행기."""

from __future__ import annotations

import argparse
import asyncio
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

from langchain_openai import ChatOpenAI

from app.core.config import PROJECT_ROOT, settings
from app.evaluation.absolute_judgment import judge_response_absolutely
from app.evaluation.service_growth_case_loading import (
    assert_service_growth_corpus_shape,
    load_service_growth_cases,
)
from app.evaluation.service_growth_contracts import (
    ServiceGrowthCase,
    ServiceGrowthCaseResult,
)
from app.evaluation.service_growth_generation import generate_service_growth_response
from app.evaluation.service_growth_report import (
    summarize_service_growth_results,
    write_service_growth_report,
)
from app.llm.registry import bootstrap as bootstrap_llms

DEFAULT_CASES = PROJECT_ROOT / "tests/evaluation/service_growth_cases.json"
DEFAULT_OUTPUT = PROJECT_ROOT / "artifacts/service_growth_eval"
DEFAULT_EVAL_USER_ID = uuid.UUID("00000000-0000-4000-8000-0000000000e1")
DEFAULT_EVAL_MANUSCRIPT_ID = uuid.UUID("00000000-0000-4000-8000-0000000000e2")

PromptInvoker = Callable[[str], str]


def _make_judge_invoker(model_name: str, api_key: str) -> PromptInvoker:
    language_model = ChatOpenAI(
        api_key=api_key,
        base_url=settings.DEEPSEEK_API_BASE,
        model=model_name,
        temperature=0,
    )

    def invoke(prompt: str) -> str:
        message = language_model.invoke(prompt)
        content = message.content
        if isinstance(content, list):
            return "".join(
                part.get("text", "") if isinstance(part, dict) else str(part)
                for part in content
            )
        return str(content)

    return invoke


def _resolve_eval_ids() -> tuple[uuid.UUID, uuid.UUID]:
    user_raw = settings.SERVICE_GROWTH_EVAL_USER_ID.strip()
    manuscript_raw = settings.SERVICE_GROWTH_EVAL_MANUSCRIPT_ID.strip()
    user_id = uuid.UUID(user_raw) if user_raw else DEFAULT_EVAL_USER_ID
    manuscript_id = (
        uuid.UUID(manuscript_raw) if manuscript_raw else DEFAULT_EVAL_MANUSCRIPT_ID
    )
    return user_id, manuscript_id


async def run_service_growth_eval(
    cases: list[ServiceGrowthCase],
    *,
    user_id: uuid.UUID,
    manuscript_id: uuid.UUID,
    judge_invoke: PromptInvoker,
) -> list[ServiceGrowthCaseResult]:
    results: list[ServiceGrowthCaseResult] = []
    for case in cases:
        try:
            response_body, evidence_text = await generate_service_growth_response(
                case,
                user_id=user_id,
                manuscript_id=manuscript_id,
            )
            if not response_body:
                results.append(
                    ServiceGrowthCaseResult(
                        case_id=case.case_id,
                        phase=case.phase,
                        claim=case.claim,
                        topic=case.topic,
                        response_body="",
                        evidence_text=evidence_text,
                        judgment=None,
                        error="empty_response",
                    )
                )
                continue
            judgment = judge_response_absolutely(
                claim=case.claim,
                topic=case.topic,
                phase=case.phase,
                response_body=response_body,
                invoke=judge_invoke,
            )
            results.append(
                ServiceGrowthCaseResult(
                    case_id=case.case_id,
                    phase=case.phase,
                    claim=case.claim,
                    topic=case.topic,
                    response_body=response_body,
                    evidence_text=evidence_text,
                    judgment=judgment,
                    error=None,
                )
            )
        except Exception as exc:
            results.append(
                ServiceGrowthCaseResult(
                    case_id=case.case_id,
                    phase=case.phase,
                    claim=case.claim,
                    topic=case.topic,
                    response_body="",
                    evidence_text="",
                    judgment=None,
                    error=f"{type(exc).__name__}: {exc}",
                )
            )
    return results


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Run service-growth absolute-score evaluation"
    )
    parser.add_argument("--cases", type=Path, default=DEFAULT_CASES)
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument(
        "--phase",
        choices=("say", "feedback", "all"),
        default="all",
    )
    parser.add_argument(
        "--skip-shape-check",
        action="store_true",
        help="limit/phase 필터 시 50건 고정 검증을 건너뛴다",
    )
    args = parser.parse_args(argv)

    api_key = settings.DEEPSEEK_API_KEY
    if not api_key:
        raise SystemExit("DEEPSEEK_API_KEY가 필요합니다.")

    bootstrap_llms(settings)
    cases = load_service_growth_cases(args.cases)
    if not args.skip_shape_check and args.limit is None and args.phase == "all":
        assert_service_growth_corpus_shape(cases)
    if args.phase != "all":
        cases = [case for case in cases if case.phase == args.phase]
    if args.limit is not None:
        cases = cases[: args.limit]
    if not cases:
        raise SystemExit("평가할 사례가 없습니다.")

    judge_model = settings.SERVICE_GROWTH_JUDGE_MODEL or settings.DEEPSEEK_MODEL
    generation_model = settings.DEEPSEEK_MODEL
    judge_invoke = _make_judge_invoker(judge_model, api_key)
    user_id, manuscript_id = _resolve_eval_ids()

    print(
        f"cases={len(cases)} generation={generation_model} judge={judge_model} "
        f"langfeather={settings.LANGFEATHER_ENABLED}"
    )
    results = asyncio.run(
        run_service_growth_eval(
            cases,
            user_id=user_id,
            manuscript_id=manuscript_id,
            judge_invoke=judge_invoke,
        )
    )
    summary = summarize_service_growth_results(
        results,
        generation_model=generation_model,
        judge_model=judge_model,
    )
    run_id = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    json_path, md_path = write_service_growth_report(
        output_dir=args.output_dir,
        results=results,
        summary=summary,
        run_id=run_id,
    )
    print(
        f"judged={summary.judged_count}/{summary.case_count} "
        f"avg_overall={summary.avg_overall} "
        f"json={json_path} md={md_path}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
