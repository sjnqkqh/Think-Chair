import os
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    GEMINI_API_KEY: str
    CHROMA_MODE: str = "local"
    CHROMA_HOST: str = "localhost"
    CHROMA_PORT: int = 8000

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
    )


settings = Settings()
