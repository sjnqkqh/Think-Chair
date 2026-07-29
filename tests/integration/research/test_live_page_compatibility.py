import os

import pytest

from app.research.contracts import FetchRequest
from app.research.page_fetcher import fetch_page


pytestmark = [
    pytest.mark.integration,
    pytest.mark.live_web,
    pytest.mark.skipif(
        os.getenv("RUN_LIVE_WEB_TESTS") != "1",
        reason="RUN_LIVE_WEB_TESTS=1일 때만 실제 웹 페이지를 요청한다.",
    ),
]


async def test_fetches_live_hugging_face_model_card():
    """Hugging Face의 현재 HTML에서도 모델 카드 본문을 추출할 수 있는지 선택적으로 검증한다."""
    response = await fetch_page(
        FetchRequest(
            url="https://huggingface.co/sentence-transformers/all-MiniLM-L6-v2"
        )
    )

    assert response.source is not None, response.error_code
    assert "sentence" in response.source.text.lower()


async def test_fetches_live_reddit_post_and_comments():
    """Reddit의 현재 HTML에서도 게시물과 댓글 출처를 분리할 수 있는지 선택적으로 검증한다."""
    response = await fetch_page(
        FetchRequest(
            url=(
                "https://www.reddit.com/r/LocalLLaMA/comments/1cvly7e/"
                "creator_of_smaug_here_clearing_up_some/"
            )
        )
    )

    assert response.source is not None, response.error_code
    assert response.source.text
    assert any(section.kind == "comment" for section in response.source.sections)
