import pytest

from app.services.evaluation_response_parser import parse_evaluation_response

pytestmark = pytest.mark.unit


def test_parse_evaluation_response_handles_valid_json():
    raw = '''{
        "score": 82,
        "verdict": "양호",
        "reason": "충실함",
        "improvements": ["a", "b"],
        "has_unnecessary_header": true,
        "has_unnecessary_footer": false
    }'''

    parsed = parse_evaluation_response(raw)

    assert parsed == {
        "score": 82,
        "verdict": "양호",
        "reason": "충실함",
        "improvements": '["a", "b"]',
        "has_unnecessary_header": True,
        "has_unnecessary_footer": False,
    }


def test_parse_evaluation_response_handles_fenced_json():
    parsed = parse_evaluation_response('```json\n{"score": 70}\n```')

    assert parsed["score"] == 70


@pytest.mark.parametrize("raw", ["이건 JSON이 아님", "[]"])
def test_parse_evaluation_response_returns_empty_result_for_invalid_payload(raw):
    parsed = parse_evaluation_response(raw)

    assert parsed == {
        "score": None,
        "verdict": None,
        "reason": None,
        "improvements": None,
        "has_unnecessary_header": None,
        "has_unnecessary_footer": None,
    }


def test_parse_evaluation_response_rejects_boolean_score():
    parsed = parse_evaluation_response('{"score": true}')

    assert parsed["score"] is None


def test_parse_evaluation_response_rejects_non_string_text_fields():
    parsed = parse_evaluation_response(
        '{"verdict": ["보완 필요"], "reason": {"detail": "근거 부족"}}'
    )

    assert parsed["verdict"] is None
    assert parsed["reason"] is None


def test_parse_evaluation_response_rejects_non_boolean_body_boundary_flags():
    parsed = parse_evaluation_response(
        '{"has_unnecessary_header": "true", "has_unnecessary_footer": 0}'
    )

    assert parsed["has_unnecessary_header"] is None
    assert parsed["has_unnecessary_footer"] is None
