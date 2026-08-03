"""개발용 AI 응답 비교 평가 CLI."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from langchain_openai import ChatOpenAI

from app.core.config import PROJECT_ROOT, settings
from app.evaluation.fixture_loading import load_response_eval_cases
from app.evaluation.report import summarize_results, write_report
from app.evaluation.runner import evaluate_case

DEFAULT_CASES = PROJECT_ROOT / "tests/evaluation/agentic_rag_cases.json"
DEFAULT_CORPUS = PROJECT_ROOT / "tests/evaluation/agentic_rag_corpus.json"
DEFAULT_OUTPUT = PROJECT_ROOT / "artifacts/ai_response_eval"


def _require_api_key() -> str:
    api_key = settings.RESPONSE_EVAL_API_KEY or settings.OPENAI_API_KEY
    if not api_key:
        raise SystemExit(
            "RESPONSE_EVAL_API_KEY 또는 OPENAI_API_KEY가 필요합니다."
        )
    return api_key


def _make_invoke(model_name: str, api_key: str):
    llm = ChatOpenAI(
        api_key=api_key,
        base_url=settings.RESPONSE_EVAL_API_BASE,
        model=model_name,
        temperature=0,
    )

    def invoke(prompt: str) -> str:
        message = llm.invoke(prompt)
        content = message.content
        if isinstance(content, list):
            return "".join(
                part.get("text", "") if isinstance(part, dict) else str(part)
                for part in content
            )
        return str(content)

    return invoke


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run AI response evaluation")
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
    cases = load_response_eval_cases(
        cases_path=args.cases,
        corpus_path=args.corpus,
        research_required_only=not args.include_non_research,
    )
    if args.limit is not None:
        cases = cases[: args.limit]
    if not cases:
        raise SystemExit("평가할 사례가 없습니다.")

    generate_invoke = _make_invoke(settings.RESPONSE_EVAL_GENERATION_MODEL, api_key)
    judge_invoke = _make_invoke(settings.RESPONSE_EVAL_JUDGE_MODEL, api_key)

    results = [
        evaluate_case(
            case,
            generate_invoke=generate_invoke,
            judge_invoke=judge_invoke,
        )
        for case in cases
    ]
    summary = summarize_results(results)
    json_path, md_path = write_report(
        output_dir=args.output_dir,
        results=results,
        summary=summary,
    )
    print(f"wrote {json_path}")
    print(f"wrote {md_path}")
    print(f"fatal_failure_count={summary.fatal_failure_count}")
    print(f"wins={summary.wins} losses={summary.losses} ties={summary.ties}")
    return 1 if summary.fatal_failure_count else 0


if __name__ == "__main__":
    sys.exit(main())
