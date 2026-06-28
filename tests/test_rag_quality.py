import os
import json
import pytest
from app.services.evaluator import EvaluatorService
from app.core.config import settings

# Skip RAG quality test if DeepSeek API Key is not configured
DEEPSEEK_KEY = settings.DEEPSEEK_API_KEY
has_deepseek_key = DEEPSEEK_KEY and DEEPSEEK_KEY != "your_deepseek_api_key_here"


@pytest.mark.skipif(
    not has_deepseek_key, reason="DEEPSEEK_API_KEY is not configured for LLM as Judge."
)
def test_rag_retrieval_and_answer_quality():
    dataset_path = os.path.join(
        settings.BASE_DIR, "tests", "data", "golden_dataset.json"
    )
    assert os.path.exists(dataset_path), "Golden dataset file does not exist."

    with open(dataset_path, "r", encoding="utf-8") as dataset_file:
        golden_dataset = json.load(dataset_file)

    evaluator_service = EvaluatorService()

    # We will use the default collection 'camp_rules' for this validation check
    collection_name = "camp_rules"

    # Check if the Chroma collection is populated
    try:
        store = evaluator_service.vector_store_manager.get_vector_store(collection_name)
        count = store._collection.count()
        if count == 0:
            pytest.skip(
                "Chroma collection 'camp_rules' is empty. Skipping RAG quality validation."
            )
    except Exception as exception:
        pytest.skip(f"Failed to connect to Chroma DB: {exception}. Skipping quality test.")

    faithfulness_scores = []
    relevance_scores = []

    for item in golden_dataset:
        question = item["question"]
        ground_truth = item["ground_truth"]

        # Run inference and get evaluation scores
        result = evaluator_service.run_evaluation_for_strategy(
            question=question,
            ground_truth=ground_truth,
            collection_name=collection_name,
            top_k=3,
        )

        scores = result["scores"]
        faithfulness_score = scores.get("faithfulness", {}).get("score", 0)
        relevance_score = scores.get("relevance", {}).get("score", 0)

        faithfulness_scores.append(faithfulness_score)
        relevance_scores.append(relevance_score)

        print(f"\nQuestion: {question}")
        print(f"Answer: {result['answer']}")
        print(f"Faithfulness Score: {faithfulness_score}/5 | Relevance Score: {relevance_score}/5")

    average_faithfulness = sum(faithfulness_scores) / len(faithfulness_scores)
    average_relevance = sum(relevance_scores) / len(relevance_scores)

    print(f"\n--- Quality Validation Summary ---")
    print(f"Average Faithfulness: {average_faithfulness:.2f}/5")
    print(f"Average Relevance: {average_relevance:.2f}/5")

    # Assert average threshold meets quality standard (e.g., >= 4.0)
    assert (
        average_faithfulness >= 4.0
    ), f"Average RAG Faithfulness ({average_faithfulness}) is below acceptable standard 4.0"
    assert (
        average_relevance >= 4.0
    ), f"Average RAG Relevance ({average_relevance}) is below acceptable standard 4.0"
