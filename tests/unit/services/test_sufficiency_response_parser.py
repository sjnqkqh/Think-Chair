import pytest

from app.services.sufficiency_response_parser import parse_sufficiency_response

pytestmark = pytest.mark.unit


def test_parse_sufficiency_response_returns_decision_for_valid_json():
    decision = parse_sufficiency_response(
        '```json\n{"sufficient": true, "reason": "근거 충분"}\n```'
    )

    assert decision is not None
    assert decision.sufficient is True
    assert decision.reason == "근거 충분"


@pytest.mark.parametrize(
    "raw_output",
    [
        "문서 본문",
        "[]",
        '{"sufficient": "true"}',
        '{"sufficient": true, "reason": []}',
        '{"sufficient": true, "extra": "형식 위반"}',
    ],
)
def test_parse_sufficiency_response_rejects_invalid_contract(raw_output):
    assert parse_sufficiency_response(raw_output) is None
