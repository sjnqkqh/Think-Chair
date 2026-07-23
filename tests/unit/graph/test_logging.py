import logging

from app.logging import get_logger


def test_event_logger_emits_event_and_fields(caplog):
    logger = get_logger("tests.graph.logging")

    with caplog.at_level(logging.INFO, logger="tests.graph.logging"):
        logger.info("evaluate_document.start", version_id="version-1", concept="essay")

    assert caplog.records[-1].message == (
        "evaluate_document.start {'version_id': 'version-1', 'concept': 'essay'}"
    )


def test_event_logger_exception_keeps_traceback(caplog):
    logger = get_logger("tests.graph.logging")

    with caplog.at_level(logging.ERROR, logger="tests.graph.logging"):
        try:
            raise ValueError("failure")
        except ValueError:
            logger.exception("evaluate_document.failed", version_id="version-1")

    assert caplog.records[-1].exc_info is not None
    assert "evaluate_document.failed" in caplog.records[-1].message


def test_event_logger_error_keeps_explicit_traceback(caplog):
    logger = get_logger("tests.graph.logging")

    try:
        raise ValueError("failure")
    except ValueError as exc:
        with caplog.at_level(logging.ERROR, logger="tests.graph.logging"):
            logger.error("background_task.failed", exc_info=exc)

    assert caplog.records[-1].exc_info is not None
    assert "background_task.failed" in caplog.records[-1].message
