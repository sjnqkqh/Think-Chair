from pathlib import Path

from app.evaluation.contracts import PreparedEvidence, ResponseComparisonCase
from app.evaluation.research_dialogue_schema import (
    EvaluationCase,
    EvaluationCorpusChunk,
    load_evaluation_cases,
    load_evaluation_corpus,
)


def load_response_comparison_cases(
    *,
    cases_path: Path,
    corpus_path: Path,
    research_required_only: bool = True,
) -> list[ResponseComparisonCase]:
    cases = load_evaluation_cases(cases_path)
    corpus = load_evaluation_corpus(corpus_path)
    selected = [
        case
        for case in cases
        if not research_required_only or case.expected_research_required
    ]
    return [to_response_comparison_case(case, corpus) for case in selected]


def to_response_comparison_case(
    case: EvaluationCase,
    corpus: list[EvaluationCorpusChunk],
) -> ResponseComparisonCase:
    allowed = tuple(case.expected_source_keys)
    forbidden = tuple(case.forbidden_source_keys)
    evidence = tuple(
        PreparedEvidence(
            source_key=chunk.source_key,
            url=chunk.url,
            title=chunk.title,
            text=chunk.text,
        )
        for chunk in corpus
        if chunk.source_key in allowed
    )
    return ResponseComparisonCase(
        case_id=case.case_id,
        ai_question=case.ai_question,
        human_response=case.human_response,
        allowed_source_keys=allowed,
        forbidden_source_keys=forbidden,
        prepared_evidence=evidence,
    )
