def test_eval_run(client, mock_evaluator):
    async def mock_run_batch(*args, **kwargs):
        return [
            {
                "strategy": "recursive (s=500, o=50)",
                "collection_name": "rag_recursive_500_50",
                "answer": "지각 3회 시 결석 처리됩니다.",
                "contexts": ["지각 3회 결석"],
                "scores": {"faithfulness": {"score": 5, "reason": "사실 기반"}},
            }
        ]

    mock_evaluator.run_batch_evaluation = mock_run_batch

    response = client.post(
        "/evaluation/run",
        json={
            "question": "지각 규정은?",
            "ground_truth": "지각 3회는 결석 1일",
            "strategies": [{"name": "recursive", "chunk_size": 500, "chunk_overlap": 50}],
            "top_k": 3,
        },
    )

    assert response.status_code == 200
    data = response.json()
    assert data["question"] == "지각 규정은?"
    assert len(data["results"]) == 1
    assert "recursive" in data["results"][0]["strategy"]
    assert data["results"][0]["scores"]["faithfulness"]["score"] == 5


def test_eval_run_json(client, mock_evaluator):
    async def mock_run_json(*args, **kwargs):
        summaries = [
            {
                "strategy": "recursive (s=500, o=50)",
                "faithfulness_avg": 5.0,
                "relevance_avg": 5.0,
                "precision_avg": 5.0,
                "recall_avg": 0.0,
                "completeness_avg": 0.0,
                "noise_ratio_avg": 0.0,
                "coverage_rate_avg": 0.0,
                "gt_match_rate_avg": 0.0,
                "avg_chunk_length_avg": 0.0,
            }
        ]
        evaluations = [
            {
                "id": 1,
                "question": "지각 규정은?",
                "ground_truth": "지각 3회는 결석 1일",
                "results": [
                    {
                        "strategy": "recursive (s=500, o=50)",
                        "collection_name": "rag_recursive_500_50",
                        "answer": "지각 3회 시 결석 처리됩니다.",
                        "contexts": ["지각 3회 결석"],
                        "scores": {"faithfulness": {"score": 5, "reason": "사실 기반"}},
                    }
                ],
            }
        ]
        return summaries, evaluations

    mock_evaluator.run_json_dataset_evaluation = mock_run_json

    response = client.post(
        "/evaluation/run-json",
        json={
            "qa_pairs": [
                {
                    "id": 1,
                    "type": "A",
                    "section": "섹션",
                    "retrieval_hint": "힌트",
                    "question": "지각 규정은?",
                    "answer": "지각 3회는 결석 1일",
                }
            ],
            "strategies": [{"name": "recursive", "chunk_size": 500, "chunk_overlap": 50}],
            "top_k": 3,
        },
    )

    assert response.status_code == 200
    data = response.json()
    assert data["summaries"][0]["faithfulness_avg"] == 5.0
    assert data["evaluations"][0]["question"] == "지각 규정은?"
