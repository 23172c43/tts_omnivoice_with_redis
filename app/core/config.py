from pydantic_settings import BaseSettings
from pathlib import Path


class Settings(BaseSettings):
    # --- App ---
    PROJECT_NAME: str = "OmniVoice API"
    DEBUG: bool = False

    # --- Redis / Celery ---
    REDIS_URL: str = "redis://localhost:6379/0"

    # --- Paths ---
    LOCAL_MODEL_DIR: str = str(
        Path(__file__).resolve().parent.parent.parent
        / "local_models" / "k2-fsa" / "OmniVoice"
    )

    # --- Server ---
    HOST: str = "0.0.0.0"
    PORT: int = 8000

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


settings = Settings()