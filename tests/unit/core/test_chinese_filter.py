import pytest

from app.core.chinese_filter import contains_chinese, sanitize_chinese

pytestmark = pytest.mark.unit


def test_contains_chinese_true():
    assert contains_chinese("漢字 test") is True


def test_contains_chinese_false():
    assert contains_chinese("한글 test") is False


def test_sanitize_chinese():
    assert sanitize_chinese("漢字 test") == " test"


def test_sanitize_chinese_no_chinese():
    assert sanitize_chinese("한글만 있는 문장") == "한글만 있는 문장"
