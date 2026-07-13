"""
Cau hinh ung dung - doc tu file .env.
Mo gia tri co the thay doi theo moi truong (dev/staging/prod).
"""

from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict

# Duong dan goc project, tu dong phat hien cho moi may
ROOT_DIR = Path(__file__).resolve().parent.parent.parent


class Settings(BaseSettings):
    """
    Cau hinh chinh cua ung dung.
    Doc gia tri tu file .env, neu khong co thi dung default.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
    )

    # --- App ---
    PROJECT_NAME: str = "OmniVoice API"
    DEBUG: bool = False

    # --- Server ---
    HOST: str = "0.0.0.0"
    PORT: int = 8000

    # --- Redis / Celery ---
    REDIS_URL: str = "redis://localhost:6379/0"

    # --- Model ---
    # Duong dan相对 project root, hoac absolute tu .env
    MODEL_DIR: str = "local_models/k2-fsa/OmniVoice"

    # --- Audio ---
    SAMPLE_RATE: int = 24000
    MAX_CHARS: int = 400

    # --- Voice ---
    DEFAULT_VOICE_ID: str = "001"


settings = Settings()


def get_model_path() -> Path:
    """
    Tra ve duong dan tuyet doi den folder model.

    Ho tro ca truong hop:
    - MODEL_DIR la relative (local_models/k2-fsa/OmniVoice)
    - MODEL_DIR la absolute (/home/user/.../OmniVoice)
    """
    model_dir = Path(settings.MODEL_DIR)
    if model_dir.is_absolute():
        return model_dir
    return ROOT_DIR / model_dir


def get_voice_ref_audio(filename: str) -> Path:
    """
    Tra ve duong dan tuyet doi den file ref_audio cua voice.

    Args:
        filename: Ten file audio (vi du: "thalicvoice_10s.mp3")

    Returns:
        Path tuyet doi den file audio
    """
    return ROOT_DIR / "app" / "services" / filename
