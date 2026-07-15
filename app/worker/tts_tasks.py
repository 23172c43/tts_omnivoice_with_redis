"""
Celery Task cho TTS - Xu ly generate audio bat dong bo.

Chuc nang:
- Non-streaming: Generate full audio, gui 1 lan cho LipSync
- Streaming: Generate tung chunk, gui tung chunk cho LipSync

Luong xu ly:
1. Generate audio tu text
2. Luu file WAV vao /dev/shm (RAM disk, chia se giua cac container)
3. Gui JSON path den LipSync service
"""

import io
import logging
import os

import soundfile as sf
import numpy as np

from app.worker.celery_app import celery_app
from app.services.omnivoice_service import generate_speech, generate_streaming

logger = logging.getLogger(__name__)

# Thu muc chia se RAM disk (tmpfs) de luu file audio
SHM_DIR = "/dev/shm/audio"

# Tao thu muc neu chua ton tai (tmpfs se empty sau moi lan reboot)
os.makedirs(SHM_DIR, exist_ok=True)

# TODO: khi nao can gui sang LipSync, uncomment dong duoi va setup .env
# from app.core.config import settings
# LIPSYNC_URL = settings.LIPSYNC_URL
# LIPSYNC_ENDPOINT = "/api/v1/lipsync/generate"


@celery_app.task(name="process_tts_task", bind=True, max_retries=2, queue="tts_queue")
def process_tts_task(self, text: str, voice_id: str = None, speed: float = None, stream: bool = False):
    """
    Celery task de xu ly yeu cau TTS.

    Quy trinh:
    1. Generate audio tu text
    2. Luu file WAV vao /dev/shm
    3. (Tuy chon) Gui audio_path + voice_id cho LipSync
       -> Hien tai dang comment, mo khi can

    Args:
        text: Van ban can chuyen thanh giong noi
        voice_id: ID cua voice (default: "001")
        speed: Toc do doc (hien tai chua ho tro)
        stream: Bat streaming mode (True: generate tung chunk)

    Returns:
        dict voi:
            - status: "success" hoac "error"
            - audio_path: Duong dan file WAV trong /dev/shm (neu thanh cong)
            - message: Thong bao loi (neu that bai)
            - mode: "streaming" hoac "non_streaming"
            - duration: Thoi gian audio (giay)

    Note:
        - File WAV duoc luu o /dev/shm (tmpfs, in-memory)
        - Can cleanup mechanism ben ngoai neu muon don dep file cu
    """
    task_id = str(self.request.id)  # ID cua Celery task, dung lam filename

    try:
        logger.info("Bat dau task TTS: task_id=%s, text=%s, voice_id=%s, stream=%s",
                     task_id, text[:50], voice_id, stream)

        if stream:
            return _handle_streaming(text, voice_id, task_id)
        else:
            return _handle_non_streaming(text, voice_id, speed, task_id)

    except Exception as exc:
        logger.error("Task TTS that bai: %s", exc, exc_info=True)

        if "CUDA" in str(exc) or "memory" in str(exc).lower():
            raise self.retry(exc=exc, countdown=60)

        return {"status": "error", "message": str(exc)}


# ============================================================
# LIPSYNC CLIENT (tam thoi comment, mo khi can)
# ============================================================

# def _send_to_lipsync(voice_id: str, audio_path: str) -> dict:
#     """
#     Gui yeu cau xu ly LipSync.
#
#     Args:
#         voice_id: ID cua voice (LipSync dung lam image_id)
#         audio_path: Duong dan file audio trong /dev/shm
#
#     Returns:
#         dict voi status va response tu LipSync.
#     """
#     payload = {
#         "image_id": voice_id,
#         "audio_path": audio_path,
#     }
#
#     try:
#         response = httpx.post(
#             f"{LIPSYNC_URL}{LIPSYNC_ENDPOINT}",
#             json=payload,
#             timeout=60,
#         )
#         response.raise_for_status()
#         return {"status": "success", "lipsync_response": response.json()}
#
#     except httpx.HTTPError as exc:
#         logger.error("Loi gui LipSync: %s", exc)
#         return {"status": "error", "message": f"Loi gui LipSync: {exc}"}
#     finally:
#         print("co ve thanh cong gui yeu cau LipSync, response: ", response.text if 'response' in locals() else 'No response')
#

# ============================================================
# STREAMING
# ============================================================

def _handle_streaming(text: str, voice_id: str, task_id: str) -> dict:
    """
    Xu ly streaming: generate tung chunk, merge, luu file WAV.

    Quy trinh:
    1. Collect tat ca chunks tu generate_streaming()
    2. Merge cac chunk thanh 1 WAV file
    3. Luu file vao /dev/shm/{task_id}.wav
    (4. Sau nay co the gui path cho LipSync neu can)

    Args:
        text: Van ban can generate
        voice_id: ID cua voice
        task_id: ID cua task (dung lam ten file)

    Returns:
        dict voi status, audio_path, duration, mode
    """
    logger.info("Streaming: collecting chunks...")

    # Buoc 1: Collect tat ca chunks
    chunks = list(generate_streaming(text, voice_id))

    if not chunks:
        return {
            "status": "error",
            "message": "Khong generate duoc chunk nao",
            "audio_path": None,
            "mode": "streaming",
        }

    logger.info("Da collect %d chunks", len(chunks))

    # Buoc 2: Merge cac chunk thanh 1 audio
    all_audio = []
    sample_rate = 24000
    for chunk in chunks:
        data, sr = sf.read(io.BytesIO(chunk))
        all_audio.append(data)
        sample_rate = sr  # Lay sample rate tu chunk cuoi

    merged = np.concatenate(all_audio)
    duration = len(merged) / sample_rate

    # Buoc 3: Luu file vao /dev/shm
    audio_path = f"{SHM_DIR}/{task_id}.wav"
    sf.write(audio_path, merged, sample_rate)

    logger.info("Da luu file: %s (%.1fs)", audio_path, duration)

    # Buoc 4 (disabled): Gui path cho LipSync khi can
    # result = _send_to_lipsync(voice_id, audio_path)

    return {
        "status": "success",
        "audio_path": audio_path,
        "mode": "streaming",
        "chunks": len(chunks),
        "duration": duration,
        "sample_rate": sample_rate,
    }


# ============================================================
# NON-STREAMING
# ============================================================

def _handle_non_streaming(text: str, voice_id: str, speed: float, task_id: str) -> dict:
    """
    Xu ly non-streaming: generate full audio, luu file WAV.

    Quy trinh:
    1. Generate full audio
    2. Luu file vao /dev/shm/{task_id}.wav
    (3. Sau nay co the gui path cho LipSync neu can)

    Args:
        text: Van ban can generate
        voice_id: ID cua voice
        speed: Toc do doc
        task_id: ID cua task (dung lam ten file)

    Returns:
        dict voi status, audio_path, duration, mode
    """
    # Buoc 1: Generate full audio
    result = generate_speech(text, voice_id, speed)

    if result["status"] != "success" or not result.get("audio_buffer"):
        return {
            "status": result.get("status", "error"),
            "message": result.get("message", "Generate speech that bai"),
            "audio_path": None,
            "mode": "non_streaming",
        }

    # Buoc 2: Luu file vao /dev/shm
    audio_path = f"{SHM_DIR}/{task_id}.wav"
    with open(audio_path, "wb") as f:
        f.write(result["audio_buffer"])

    # Tinh duration tu buffer size (16-bit mono WAV = sample_rate * 2 bytes)
    buffer = result["audio_buffer"]
    duration = len(buffer) / (24000 * 2)

    logger.info("Da luu file: %s (%d bytes, %.1fs)", audio_path, len(buffer), duration)

    # Buoc 3 (disabled): Gui path cho LipSync khi can
    # result = _send_to_lipsync(voice_id, audio_path)

    return {
        "status": "success",
        "audio_path": audio_path,
        "mode": "non_streaming",
        "duration": duration,
    }
