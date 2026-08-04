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
    DEEPSEEK_MODEL: str = "deepseek-chat"
    BRAVE_SEARCH_API_KEY: str = ""
    OPENAI_API_KEY: str = ""

    # AI response comparison (separate from document evaluation)
    RESPONSE_COMPARISON_API_KEY: str = ""
    RESPONSE_COMPARISON_API_BASE: str = "https://api.openai.com/v1"
    RESPONSE_COMPARISON_GENERATION_MODEL: str = "gpt-4.1-mini"
    RESPONSE_COMPARISON_JUDGE_MODEL: str = "gpt-4.1"

    # Think Chair
    JWT_SECRET: str = "dev-secret-change-me"
    JWT_TTL_HOURS: int = 24
    DATA_ROOT: Path = PROJECT_ROOT
    STORAGE_ROOT: Path = Path.home() / "storage"
    CHROMA_ROOT: Path = PROJECT_ROOT / "chroma_db"

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
