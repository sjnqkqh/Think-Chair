from unittest.mock import MagicMock

import pytest

from app.services.document_evaluation_service import save_document_evaluation

pytestmark = pytest.mark.unit

_MANUSCRIPT_ID = "11111111-1111-1111-1111-111111111111"
_VERSION_ID = "22222222-2222-2222-2222-222222222222"


def test_save_document_evaluation_persists_normalized_result():
    db = MagicMock()

    save_document_evaluation(
        db,
        _MANUSCRIPT_ID,
        _VERSION_ID,
        '{"score": 70}',
        "checklist-1",
        {
            "score": 70,
            "verdict": "보완 필요",
            "reason": "근거 부족",
            "improvements": '["수치 추가"]',
            "has_unnecessary_header": True,
            "has_unnecessary_footer": False,
        },
    )

    db.add.assert_called_once()
    saved = db.add.call_args.args[0]
    assert str(saved.manuscript_id) == _MANUSCRIPT_ID
    assert str(saved.version_id) == _VERSION_ID
    assert saved.score == 70
    assert saved.has_unnecessary_header is True
    assert saved.has_unnecessary_footer is False
    assert saved.checklist_id == "checklist-1"
    db.commit.assert_called_once()
