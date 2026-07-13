"""
OmniVoice TTS Service - Dich vu chuyen van ban thanh giong noi.

Chuc nang chinh:
- Tai model OmniVoice tu HuggingFace (neu chua co)
- Generate audio tu text voi voice cloning
- Streaming: chia text thanh cau, generate tung chunk

Voice Registry:
- Luu tru cau hinh voice (ref_audio, ref_text) cho tung voice_id
- Mo voice la mot file audio mau + van ban mau
"""

import io
import logging
import re
from pathlib import Path
from typing import Iterator, Optional

import soundfile as sf
import torch

from app.core.config import settings, get_model_path, get_voice_ref_audio
from app.utils.normalizer import normalize_number_input

logger = logging.getLogger(__name__)

# --- VOICE REGISTRY ---
# Mo voice id = mot bo (ref_audio, ref_text) dung de clone giong
# ref_audio: file audio mau (10-20s)
# ref_text: noi dung cua file audio mau (de model hieu)
VOICE_REGISTRY = {
    "001": {
        "ref_audio": "thalicvoice_10s.mp3",
        "ref_text": (
            "Mot so tinh mien bac, luu y khong phai la tat ca se gap mot so van de "
            "ve phat am nhu bi ngong l, n hay la bi sai nguyen am. Va muon chuyen "
            "sang giong Ha Noi chung phai khac phuc hai nguyen nay."
        ),
    },
    # Them voice moi o day:
    # "002": {
    #     "ref_audio": "voice_002.mp3",
    #     "ref_text": "Van ban mau cua voice 002...",
    # },
}

# --- BIEN TOAN CUC ---
_model_instance = None  # Singleton model instance
MODEL_DOWNLOADED = False  # Kiem tra model da tai chua


# ============================================================
# MODEL MANAGEMENT
# ============================================================

def ensure_model_downloaded() -> bool:
    """
    Kiem tra va tai model tu HuggingFace neu chua co.

    Quy trinh:
    1. Kiem tra file config.json co ton tai trong MODEL_DIR khong
    2. Neu co -> danh dau da tai
    3. Neu khong -> goi huggingface_hub.snapshot_download de tai ve
    4. Tai thanh cong -> danh dau MODEL_DOWNLOADED = True
    5. Tai that bai -> log loi, tra ve False

    Returns:
        True neu model da san sang, False neu khong the tai
    """
    global MODEL_DOWNLOADED

    # Neu da tai roi thi khong can kiem tra lai
    if MODEL_DOWNLOADED:
        return True

    # Kiem tra file config.json co ton tai khong
    model_path = get_model_path()
    config_file = model_path / "config.json"
    if config_file.exists():
        MODEL_DOWNLOADED = True
        logger.info("Model da ton tai tai: %s", model_path)
        return True

    # Chua co -> tai tu HuggingFace
    logger.info("Dang tai model tu HuggingFace ve: %s ...", model_path)
    try:
        from huggingface_hub import snapshot_download

        # Tai model ve local, khong dung symlinks de hoat dong offline
        snapshot_download(
            repo_id="k2-fsa/OmniVoice",
            local_dir=str(model_path),
            local_dir_use_symlinks=False,
            resume_download=True,  # Ho tro tai lai neu bi gian doan
        )
        MODEL_DOWNLOADED = True
        logger.info("Tai model thanh cong!")
        return True
    except Exception as exc:
        logger.error("Tai model that bai: %s", exc, exc_info=True)
        return False


def get_model():
    """
    Load model OmniVoice vao GPU (chi 1 lan duy nhat).

    Quy trinh:
    1. Kiem tra model da load chua (_model_instance)
    2. Neu chua -> kiem tra da tai chua
    3. Tai model tu local dir vao GPU (device_map="cuda:0")
    4. Su dung dtype=float16 de giam nho bo nho
    5. Chi can TTS (load_asr=False) de nhanh hon

    Returns:
        Model instance da load vao GPU

    Raises:
        RuntimeError: Neu model chua duoc tai
    """
    global _model_instance

    # Tra ve instance da load (singleton pattern)
    if _model_instance is not None:
        return _model_instance

    # Kiem tra model da tai chua
    if not ensure_model_downloaded():
        raise RuntimeError(
            "Model OmniVoice chua duoc tai. Kiem tra ket noi mang hoac "
            f"tai thu cong vao: {get_model_path()}"
        )

    # Lazy import - chi import khi can thiet
    from omnivoice import OmniVoice

    logger.info("Dang nap model OmniVoice vao GPU...")
    _model_instance = OmniVoice.from_pretrained(
        str(get_model_path()),
        device_map="cuda:0",      # GPU 0
        dtype=torch.float16,      # FP16 de giam nho
        load_asr=False,           # Chi can TTS
        local_files_only=True,    # Khong download lai
    )
    logger.info("Nap model thanh cong!")
    return _model_instance


# ============================================================
# VOICE MANAGEMENT
# ============================================================

def get_voice_config(voice_id: str = None) -> dict:
    """
    Lay cau hinh voice tu registry.

    Args:
        voice_id: ID cua voice (vi du: "001"). Neu khong truyen -> su dung DEFAULT_VOICE_ID

    Returns:
        dict voi:
            - ref_audio: Path tuyet doi den file audio mau
            - ref_text: Van ban mau cua voice

    Example:
        >>> config = get_voice_config("001")
        >>> config["ref_audio"]
        Path("/home/.../thalicvoice_10s.mp3")
    """
    # Su dung voice_id hoac default
    vid = voice_id or settings.DEFAULT_VOICE_ID

    # Tim kiem trong registry
    config = VOICE_REGISTRY.get(vid)
    if not config:
        logger.warning(
            "Voice '%s' khong tim thay, dung mac dinh '%s'",
            vid,
            settings.DEFAULT_VOICE_ID,
        )
        config = VOICE_REGISTRY[settings.DEFAULT_VOICE_ID]

    # Chuyen thanh absolute path
    ref_audio = get_voice_ref_audio(config["ref_audio"])
    return {
        "ref_audio": ref_audio,
        "ref_text": config["ref_text"],
    }


# ============================================================
# AUDIO GENERATION
# ============================================================

def generate_speech(
    text: str,
    voice_id: Optional[str] = None,
    speed: float = 1.0,
) -> dict:
    """
    Generate audio tu van ban (non-streaming).

    Quy trinh:
    1. Lay cau hinh voice (ref_audio, ref_text) tu voice_id
    2. Chuan hoa van ban (so, don vi...)
    3. Load model neu chua co
    4. Kiem tra file ref_audio ton tai
    5. Goi model.generate() de tao audio
    6. Chuyen audio thanh WAV buffer
    7. Tra ve dict voi audio_buffer

    Args:
        text: Van ban can chuyen thanh giong noi
        voice_id: ID cua voice (default: "001")
        speed: Toc do doc (0.5-2.0, hien tai chua ho tro)

    Returns:
        dict voi:
            - status: "success" hoac "error"
            - audio_buffer: bytes cua file WAV (neu thanh cong)
            - message: Thong bao loi (neu that bai)

    Example:
        >>> result = generate_speech("Xin chao cac ban", voice_id="001")
        >>> if result["status"] == "success":
        ...     with open("output.wav", "wb") as f:
        ...         f.write(result["audio_buffer"])
    """
    # Buoc 1: Lay cau hinh voice
    voice_config = get_voice_config(voice_id)
    ref_audio = voice_config["ref_audio"]
    ref_text = voice_config["ref_text"]

    # Buoc 2: Chuan hoa van ban (so thanh chu, don vi...)
    normalized = normalize_number_input(text)
    logger.info("Generate: voice=%s, text_len=%d", voice_id, len(normalized))

    # Buoc 3: Load model (tra ve instance da load)
    try:
        model = get_model()
    except RuntimeError as exc:
        return {"status": "error", "audio_buffer": None, "message": str(exc)}

    # Buoc 4: Kiem tra file ref_audio ton tai
    if not ref_audio.exists():
        return {
            "status": "error",
            "audio_buffer": None,
            "message": f"Khong tim thay file audio mau: {ref_audio}",
        }

    # Buoc 5-6: Generate audio va chuyen thanh WAV buffer
    try:
        audio = model.generate(
            text=normalized,
            ref_audio=str(ref_audio),
            ref_text=ref_text,
        )

        # Chuyen numpy array -> WAV bytes
        buffer = io.BytesIO()
        sf.write(buffer, audio[0], settings.SAMPLE_RATE, format="wav")
        buffer.seek(0)

        return {
            "status": "success",
            "audio_buffer": buffer.read(),
            "message": "Tao am thanh thanh cong",
        }
    except Exception as exc:
        logger.error("Generate speech that bai: %s", exc, exc_info=True)
        return {"status": "error", "audio_buffer": None, "message": f"Loi generate: {exc}"}


# ============================================================
# STREAMING
# ============================================================

# Regex: tach theo dau cau . ! ? hoac dau cau Trung Nhat
_SENTENCE_END = re.compile(
    r"(?<=[.!?])\s+(?=[A-ZÀ-ɏḀ-ỿ])"  # Latin: . ! ? + space + Capital
    r"|(?<=[。！？])"  # CJK: 。！？
)

# Regex: phan biet false boundaries (so thap phan, ten viet tat, URL)
_FALSE_ENDS = re.compile(
    r"\d+\.\d+"           # So thap phan: 3.14
    r"|[A-Z][a-z]{0,3}\." # Ten viet tat: Mr. Dr.
    r"|\w+\.\w{2,6}(?:/|\s|$)"  # URL/file: example.com
)


def split_sentences(text: str, max_chars: int = None) -> list[str]:
    """
    Chia text thanh cac chunk phu hop cho streaming.

    Quy trinh:
    1. Neu text ngan hon max_chars -> tra ve nguyen 1 chunk
    2. Tach theo dau cau (. ! ? hoac 。！？)
    3. Gop cac false boundaries (3.14, Mr., example.com)
    4. Gop cac chunk ngan de dat max_chars
    5. Neu van con chunk dai -> tach theo tu

    Args:
        text: Van ban can chia
        max_chars: So ky tu toi da moi chunk (default: tu settings)

    Returns:
        list cac chunk, moi chunk <= max_chars ky tu

    Example:
        >>> split_sentences("Xin chao. Ban khoi khong?", max_chars=20)
        ['Xin chao.', 'Ban khoi khong?']
    """
    if max_chars is None:
        max_chars = settings.MAX_CHARS

    if not text or not text.strip():
        return []

    text = text.strip()

    # Neu ngan hon max_chars -> tra ve 1 chunk
    if len(text) <= max_chars:
        return [text]

    # Buoc 1: Tach theo dau cau
    raw_sentences = _SENTENCE_END.split(text)
    raw_sentences = [s.strip() for s in raw_sentences if s.strip()]

    if not raw_sentences:
        return [text]

    # Buoc 2: Gop false boundaries (3.14, Mr., example.com)
    merged: list[str] = []
    i = 0
    while i < len(raw_sentences):
        current = raw_sentences[i]
        # Kiem tra xem co false boundary khong
        while i + 1 < len(raw_sentences):
            match = None
            for m in _FALSE_ENDS.finditer(current):
                match = m
            # Neu match o cuoi cau -> gop voi cau tiep theo
            if match and match.end() >= len(current) - 2:
                current = current + " " + raw_sentences[i + 1]
                i += 1
            else:
                break
        merged.append(current)
        i += 1

    # Buoc 3: Gop cac chunk ngan de dat max_chars
    chunks: list[str] = []
    current = ""
    for sentence in merged:
        if not current:
            current = sentence
        elif len(current) + 1 + len(sentence) <= max_chars:
            current = current + " " + sentence
        else:
            chunks.append(current)
            current = sentence
    if current:
        chunks.append(current)

    # Buoc 4: Neu van con chunk dai -> tach theo tu
    result: list[str] = []
    for chunk in chunks:
        if len(chunk) <= max_chars:
            result.append(chunk)
        else:
            words = chunk.split()
            part = ""
            for word in words:
                if not part:
                    part = word
                elif len(part) + 1 + len(word) <= max_chars:
                    part += " " + word
                else:
                    result.append(part)
                    part = word
            if part:
                result.append(part)

    return [c for c in result if c.strip()]


def generate_streaming(
    text: str,
    voice_id: str = None,
    max_chars: int = None,
    sample_rate: int = None,
) -> Iterator[bytes]:
    """
    Generate streaming audio tu van ban.

    Chia text thanh tung chunk (theo cau), generate tung chunk,
    va yield buffer ngay de gui den service khac.

    Quy trinh:
    1. Load model (neu chua co)
    2. Lay cau hinh voice tu voice_id
    3. Chuan hoa van ban
    4. Chia text thanh cac chunk (split_sentences)
    5. Voi moi chunk:
       a. Goi model.generate() de tao audio
       b. Chuyen thanh WAV bytes
       c. Yield buffer ngay (khong wait chunk khac)

    Args:
        text: Van ban can generate
        voice_id: ID cua voice (default: "001")
        max_chars: So ky tu toi da moi chunk (default: tu settings)
        sample_rate: Tan so mau (default: tu settings)

    Yields:
        bytes cua file WAV moi chunk

    Example:
        >>> for chunk in generate_streaming("Xin chao...", voice_id="001"):
        ...     send_to_lipsync(chunk)

    Note:
        - Chunk dau tien la nhanh nhat (khong can wait)
        - Mo chunk la 1 cau hoac nhieu cau ngan
        - Chunk cuoi co the ngan hon max_chars
    """
    if max_chars is None:
        max_chars = settings.MAX_CHARS
    if sample_rate is None:
        sample_rate = settings.SAMPLE_RATE

    # Buoc 1: Load model
    model = get_model()

    # Buoc 2: Lay cau hinh voice
    voice_config = get_voice_config(voice_id)
    ref_audio = str(voice_config["ref_audio"])
    ref_text = voice_config["ref_text"]

    # Buoc 3: Chuan hoa van ban
    normalized = normalize_number_input(text)

    # Buoc 4: Chia thanh cac chunk
    sentences = split_sentences(normalized, max_chars)

    if not sentences:
        logger.warning("Khong co cau nao de generate")
        return

    logger.info("Streaming %d chunks, voice=%s", len(sentences), voice_id)

    # Buoc 5: Generate tung chunk va yield ngay
    for i, sentence in enumerate(sentences):
        logger.info("Chunk %d/%d: %s", i + 1, len(sentences), sentence[:50])

        # Generate audio cho 1 chunk
        audio = model.generate(
            text=sentence,
            ref_audio=ref_audio,
            ref_text=ref_text,
        )

        # Chuyen thanh WAV bytes va yield
        buffer = io.BytesIO()
        sf.write(buffer, audio[0], sample_rate, format="wav")
        buffer.seek(0)

        yield buffer.read()
