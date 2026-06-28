import os
from dotenv import load_dotenv
from pydantic_settings import BaseSettings, SettingsConfigDict

# Load environment variables into os.environ for LangChain/LangSmith
load_dotenv()


class Settings(BaseSettings):
    GEMINI_API_KEY: str
    CHROMA_MODE: str = "local"
    CHROMA_HOST: str = "localhost"
    CHROMA_PORT: int = 8000

    DEEPSEEK_API_KEY: str = ""
    DEEPSEEK_API_BASE: str = "https://api.deepseek.com"
    DEEPSEEK_MODEL: str = "deepseek-chat"

    @property
    def BASE_DIR(self) -> str:
        return os.path.dirname(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        )

    @property
    def CHROMA_DB_PATH(self) -> str:
        return os.path.join(self.BASE_DIR, "chroma_db")

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
