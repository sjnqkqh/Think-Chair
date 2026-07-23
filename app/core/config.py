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

    # Think Chair
    JWT_SECRET: str = "dev-secret-change-me"
    JWT_TTL_HOURS: int = 24
    DATA_ROOT: Path = PROJECT_ROOT
    STORAGE_ROOT: Path = Path.home() / "storage"

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
