import logging
import torch
import soundfile as sf
import psutil
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# --- THIET LAP DUONG DAN CHUAN ---
HERE = Path(__file__).resolve().parent
ROOT_DIR = HERE.parent.parent          # /home/.../TTS_Endpoint
LOCAL_MODEL_DIR = ROOT_DIR / "local_models" / "k2-fsa" / "OmniVoice"
SERVICES_DIR = HERE
OUTPUT_DIR = SERVICES_DIR

OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
LOCAL_MODEL_DIR.mkdir(parents=True, exist_ok=True)

SAMPLE_AUDIO_PATH = SERVICES_DIR / "thalicvoice_10s.mp3"
OUTPUT_AUDIO_PATH = OUTPUT_DIR / "output.wav"

MODEL_DOWNLOADED = (LOCAL_MODEL_DIR / "config.json").exists()

_model_instance = None


def ensure_model_downloaded():
    """Tai model neu chua co (duoc goi 1 lan duy nhat khi can)."""
    global MODEL_DOWNLOADED
    if MODEL_DOWNLOADED:
        return True

    if (LOCAL_MODEL_DIR / "config.json").exists():
        MODEL_DOWNLOADED = True
        return True

    logger.info("Khong tim thay model local. Dang tai ve: %s ...", LOCAL_MODEL_DIR)
    try:
        from huggingface_hub import snapshot_download
        snapshot_download(
            repo_id="k2-fsa/OmniVoice",
            local_dir=str(LOCAL_MODEL_DIR),
            local_dir_use_symlinks=False,
            resume_download=True,
        )
        MODEL_DOWNLOADED = True
        logger.info("Tai model thanh cong!")
        return True
    except Exception as exc:
        logger.error("Tai model that bai: %s", exc, exc_info=True)
        return False


def get_model():
    """Load model vao GPU (chi 1 lan)."""
    global _model_instance
    if _model_instance is not None:
        return _model_instance

    if not ensure_model_downloaded():
        raise RuntimeError(
            "Model OmniVoice chua duoc tai. Kiem tra ket noi mang hoac "
            f"tai thu cong vao: {LOCAL_MODEL_DIR}"
        )

    from omnivoice import OmniVoice  # lazy import tranh dependency tai startup

    logger.info("Lan goi API dau tien: Dang nap model OmniVoice vao GPU...")
    _model_instance = OmniVoice.from_pretrained(
        str(LOCAL_MODEL_DIR),
        device_map="cuda:0",
        dtype=torch.float16,
        load_asr=False,
        local_files_only=True,
    )
    logger.info("Nap model thanh cong!")
    return _model_instance


def generate_speech(
    text: str,
    voice_id: Optional[str] = None,
    speed: float = 1.0,
) -> dict:
    """
    Chuan hoa -> OmniVoice -> ghi file am thanh -> tra ve duong dan.
    """
    from app.utils.normalizer import normalize_number_input

    # Chuan hoa van ban
    normalized = normalize_number_input(text)
    logger.info("Van ban sau chuan hoa: %s", normalized[:100])

    # Lay model instance
    try:
        model = get_model()
    except RuntimeError as exc:
        return {"status": "error", "audio_url": None, "message": str(exc)}

    # Check reference audio
    if not SAMPLE_AUDIO_PATH.exists():
        return {
            "status": "error",
            "audio_url": None,
            "message": f"Khong tim thay file audio mau: {SAMPLE_AUDIO_PATH}",
        }

    reference_text = (
        "Một số tỉnh miền bắc, lưu ý không phải là tất cả sẽ gặp một số vấn đề "
        "về phát âm như là bị ngọng l, n hay là bị sai nguyên âm. Và muốn chuyển "
        "sang giọng Hà Nội chúng phải khắc phục hai nguyên nhân này."
    )

    logger.info(
        "Dang generate: voice_id=%s, speed=%s, text_len=%d",
        voice_id, speed, len(normalized),
    )

    try:
        audio = model.generate(
            text=normalized,
            ref_audio=str(SAMPLE_AUDIO_PATH),
            ref_text=reference_text,
        )

        sf.write(str(OUTPUT_AUDIO_PATH), audio[0], 24000)

        mem = psutil.Process().memory_info().rss / 1024**3
        logger.info(
            "Tao am thanh thanh cong: %s (%.1f MB, RSS=%.2f GB)",
            OUTPUT_AUDIO_PATH, OUTPUT_AUDIO_PATH.stat().st_size / 1024**2, mem,
        )

        return {
            "status": "success",
            "audio_url": str(OUTPUT_AUDIO_PATH),
            "message": "Tao am thanh thanh cong",
        }

    except Exception as exc:
        logger.error("Generate speech that bai: %s", exc, exc_info=True)
        return {
            "status": "error",
            "audio_url": None,
            "message": f"Loi generate: {exc}",
        }