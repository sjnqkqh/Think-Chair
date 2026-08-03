"""개발용 AI 응답 비교 평가 실행기."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Callable

from langchain_openai import ChatOpenAI

from app.core.config import PROJECT_ROOT, settings
from app.evaluation.comparison_case_loading import load_response_comparison_cases
from app.evaluation.report import summarize_comparison_results, write_comparison_report
from app.evaluation.runner import compare_case_responses

DEFAULT_CASES = PROJECT_ROOT / "tests/evaluation/agentic_rag_cases.json"
DEFAULT_CORPUS = PROJECT_ROOT / "tests/evaluation/agentic_rag_corpus.json"
DEFAULT_OUTPUT = PROJECT_ROOT / "artifacts/ai_response_comparison"
# 사례당 대략 생성 2회 + 판정 2회. 한도는 fixture 개수이며 코드상 상한은 없다.
API_CALLS_PER_CASE = 4

PromptInvoker = Callable[[str], str]


def _require_api_key() -> str:
    api_key = settings.RESPONSE_COMPARISON_API_KEY or settings.OPENAI_API_KEY
    if not api_key:
        raise SystemExit(
            "RESPONSE_COMPARISON_API_KEY 또는 OPENAI_API_KEY가 필요합니다."
        )
    return api_key


def _make_prompt_invoker(model_name: str, api_key: str) -> PromptInvoker:
    language_model = ChatOpenAI(
        api_key=api_key,
        base_url=settings.RESPONSE_COMPARISON_API_BASE,
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


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run AI response comparison evaluation")
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--cases", type=Path, default=DEFAULT_CASES)
    parser.add_argument("--corpus", type=Path, default=DEFAULT_CORPUS)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument(
        "--include-non-research",
        action="store_true",
        help="조사 불필요 사례도 포함",
    )
    args = parser.parse_args(argv)

    api_key = _require_api_key()
    cases = load_response_comparison_cases(
        cases_path=args.cases,
        corpus_path=args.corpus,
        research_required_only=not args.include_non_research,
    )
    if args.limit is not None:
        cases = cases[: args.limit]
    if not cases:
        raise SystemExit("평가할 사례가 없습니다.")

    estimated_calls = len(cases) * API_CALLS_PER_CASE
    print(
        f"cases={len(cases)} estimated_llm_calls≈{estimated_calls} "
        f"(약 {API_CALLS_PER_CASE}회/사례, 상한은 fixture 수·API 한도)"
    )

    generate_invoke = _make_prompt_invoker(
        settings.RESPONSE_COMPARISON_GENERATION_MODEL, api_key
    )
    judge_invoke = _make_prompt_invoker(
        settings.RESPONSE_COMPARISON_JUDGE_MODEL, api_key
    )

    results = [
        compare_case_responses(
            case,
            generate_invoke=generate_invoke,
            judge_invoke=judge_invoke,
        )
        for case in cases
    ]
    summary = summarize_comparison_results(results)
    json_path, markdown_path = write_comparison_report(
        output_dir=args.output_dir,
        results=results,
        summary=summary,
    )
    print(f"wrote {json_path}")
    print(f"wrote {markdown_path}")
    print(f"fatal_failure_count={summary.fatal_failure_count}")
    print(f"wins={summary.wins} losses={summary.losses} ties={summary.ties}")
    return 1 if summary.fatal_failure_count else 0


if __name__ == "__main__":
    sys.exit(main())
