from app.llm.deepseek_call_log import DeepSeekGraphCallLogger, _purpose_from_metadata


def test_purpose_from_langgraph_node_metadata():
    assert _purpose_from_metadata({"langgraph_node": "converse"}) == "chat.converse"
    assert _purpose_from_metadata({}) == "chat.unknown"
    assert _purpose_from_metadata(None) == "chat.unknown"


def test_graph_call_logger_emits_purpose(caplog):
    import logging

    handler = DeepSeekGraphCallLogger()
    with caplog.at_level(logging.INFO):
        handler.on_chat_model_start(
            {},
            [{"role": "user"}],
            run_id="00000000-0000-0000-0000-000000000001",
            metadata={"langgraph_node": "router"},
        )
    assert any("llm.deepseek.request" in r.message for r in caplog.records)
    assert any("chat.router" in r.message for r in caplog.records)
