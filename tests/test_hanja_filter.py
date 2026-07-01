from app.core.hanja_filter import contains_hanja, sanitize_hanja


def test_contains_hanja_true():
    assert contains_hanja("漢字 test") is True


def test_contains_hanja_false():
    assert contains_hanja("한글 test") is False


def test_sanitize_hanja():
    assert sanitize_hanja("漢字 test") == " test"


def test_sanitize_hanja_no_hanja():
    assert sanitize_hanja("한글만 있는 문장") == "한글만 있는 문장"
