import os
from pathlib import Path
from dotenv import load_dotenv
from pydantic_settings import BaseSettings, SettingsConfigDict

# Load environment variables into os.environ for LangChain/LangSmith
load_dotenv()

PROJECT_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    DEEPSEEK_API_KEY: str = ""
    DEEPSEEK_API_BASE: str = "https://api.deepseek.com"
    DEEPSEEK_MODEL: str = "deepseek-v4-flash"
    BRAVE_SEARCH_API_KEY: str = ""
    OPENAI_API_KEY: str = ""
    OPENAI_API_BASE: str = "https://api.openai.com/v1"
    OPENAI_MODEL: str = "gpt-5.6-luna"
    # 서버 기동 시 deepseek/openai 기본 모델 호출 가능 여부를 검증한다.
    LLM_STARTUP_VERIFY: bool = True

    # Service-growth absolute eval (product nodes + public index)
    SERVICE_GROWTH_JUDGE_MODEL: str = ""  # empty → DEEPSEEK_MODEL
    SERVICE_GROWTH_EVAL_USER_ID: str = ""
    SERVICE_GROWTH_EVAL_MANUSCRIPT_ID: str = ""

    # Think Chair
    JWT_SECRET: str = "dev-secret-change-me"
    JWT_TTL_HOURS: int = 24
    DATA_ROOT: Path = PROJECT_ROOT
    STORAGE_ROOT: Path = Path.home() / "storage"
    CHROMA_ROOT: Path = PROJECT_ROOT / "chroma_db"
    # Compose 기본값과 동일. 테스트는 conftest에서 sqlite:// 로 덮어쓴다.
    DATABASE_URL: str = (
        "postgresql+psycopg://thinkchair:thinkchair@localhost:5432/thinkchair"
    )

    # Local LangFeather observability (collector: 127.0.0.1:4319)
    LANGFEATHER_ENABLED: bool = False
    LANGFEATHER_ENDPOINT: str = "http://127.0.0.1:4319"

    @property
    def BASE_DIR(self) -> str:
        return str(PROJECT_ROOT)

    model_config = SettingsConfigDict(
        env_file=os.path.join(
            os.path.dirname(
                os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            ),
            ".env",
        ),
        env_file_encoding="utf-8",
        extra="ignore",
    )


settings = Settings()
