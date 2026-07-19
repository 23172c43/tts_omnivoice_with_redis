"""
Voice management endpoints - Quan ly giong noi.

Endpoints:
- GET /voices: Danh sach tat ca voices
- POST /voices: Them voice moi (upload audio + transcript)
- DELETE /voices/{voice_id}: Xoa voice
"""

import json
import logging
from pathlib import Path

from fastapi import APIRouter, File, Form, HTTPException, UploadFile, status

from app.core.config import ROOT_DIR
from app.schemas.voice import VoiceInfo, VoiceUploadResponse
from app.services.omnivoice_service import _scan_voice_data, VOICE_DATA_DIR

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/voices", tags=["Voice Management"])

# File extensions cho phep
ALLOWED_EXTENSIONS = {".mp3", ".wav"}
MAX_FILE_SIZE = 10 * 1024 * 1024  # 10MB


def _next_voice_id() -> str:
    """Tim voice_id tiep theo (tang dan: 001, 002, 003...)."""
    if not VOICE_DATA_DIR.exists():
        return "001"

    existing = []
    for folder in VOICE_DATA_DIR.iterdir():
        if folder.is_dir() and folder.name.isdigit():
            existing.append(int(folder.name))

    if not existing:
        return "001"

    next_id = max(existing) + 1
    return f"{next_id:03d}"


# ============================================================
# GET /voices
# ============================================================

@router.get("/", response_model=list[VoiceInfo])
async def list_voices():
    """
    Lay danh sach tat ca voices.

    Returns:
        list[VoiceInfo]: Moi voice co voice_id, name, ref_text

    Example:
        >>> GET /api/v1/voices/
        >>> [{"voice_id": "001", "name": "Giọng Tô Vĩnh Diện", "ref_text": "..."}]
    """
    # Scan lai de lay du lieu moi nhat
    _scan_voice_data()

    # Lay registry tu cache
    from app.services.omnivoice_service import _voice_data_cache

    if not _voice_data_cache:
        return []

    voices = []
    for vid, config in _voice_data_cache.items():
        voices.append(VoiceInfo(
            voice_id=vid,
            name=config.get("name", vid),
            ref_text=config.get("ref_text", ""),
        ))

    return voices


# ============================================================
# POST /voices
# ============================================================

@router.post("/", response_model=VoiceUploadResponse, status_code=status.HTTP_201_CREATED)
async def upload_voice(
    file: UploadFile = File(..., description="File audio (.mp3 hoac .wav)"),
    name: str = Form(..., description="Ten de goi voice (vi du: 'Giọng Hà Nội')"),
    transcript: str = Form(..., description="Van ban mau (ref_text) cua voice"),
):
    """
    Them voice moi.

    Quy trinh:
    1. Kiem tra file audio hop le (.mp3/.wav, toi da 10MB)
    2. Tao folder moi voi voice_id tang dan (001, 002, 003...)
    3. Luu file audio vao folder
    4. Luu ref.txt (transcript)
    5. Luu meta.json (name)
    6. Tra ve voice_id moi

    Args:
        file: File audio upload
        name: Ten de goi voice
        transcript: Van ban mau (ref_text)

    Returns:
        VoiceUploadResponse voi voice_id, name, message

    Example:
        >>> POST /api/v1/voices/
        >>> Form: file=@audio.mp3, name="Giọng Hà Nội", transcript="Xin chào..."
        >>> Response: {"voice_id": "003", "name": "Giọng Hà Nội", "message": "Thanh cong"}
    """
    # Kiem tra file extension
    if not file.filename:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="File khong co ten.",
        )

    ext = Path(file.filename).suffix.lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"File khong ho tro. Chi chap nhan: {', '.join(ALLOWED_EXTENSIONS)}",
        )

    # Kiem tra file size
    content = await file.read()
    if len(content) > MAX_FILE_SIZE:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"File qua lon. toi da {MAX_FILE_SIZE // (1024 * 1024)}MB.",
        )

    # Tao voice_id moi
    voice_id = _next_voice_id()
    voice_dir = VOICE_DATA_DIR / voice_id

    try:
        voice_dir.mkdir(parents=True, exist_ok=True)

        # Luu file audio
        audio_path = voice_dir / f"ref_audio{ext}"
        with open(audio_path, "wb") as f:
            f.write(content)

        # Luu ref.txt
        ref_path = voice_dir / "ref.txt"
        ref_path.write_text(transcript.strip(), encoding="utf-8")

        # Luu meta.json
        meta_path = voice_dir / "meta.json"
        meta_path.write_text(json.dumps({"name": name}, ensure_ascii=False, indent=2), encoding="utf-8")

        logger.info("Voice moi da duoc tao: %s (%s)", voice_id, name)

        # Xoa cache de scan lai
        from app.services.omnivoice_service import _voice_data_cache, _voice_data_mtime
        import app.services.omnivoice_service as svc
        svc._voice_data_cache = None
        svc._voice_data_mtime = 0

        return VoiceUploadResponse(
            voice_id=voice_id,
            name=name,
            message=f"Voice '{name}' da duoc them thanh cong.",
        )

    except Exception as exc:
        logger.error("Loi khi tao voice: %s", exc, exc_info=True)
        # Rollback: xoa folder neu co loi
        if voice_dir.exists():
            import shutil
            shutil.rmtree(voice_dir, ignore_errors=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Khong the tao voice: {exc}",
        )


# ============================================================
# DELETE /voices/{voice_id}
# ============================================================

@router.delete("/{voice_id}", status_code=status.HTTP_200_OK)
async def delete_voice(voice_id: str):
    """
    Xoa voice theo voice_id.

    Xoa toan bo folder voice_data/{voice_id}/ (bao gom audio, ref.txt, meta.json).

    Args:
        voice_id: ID cua voice can xoa (vi du: "002")

    Returns:
        dict voi message thong bao thanh cong

    Example:
        >>> DELETE /api/v1/voices/002
        >>> Response: {"message": "Voice 'Giọng Võ Thị Sáu' da duoc xoa."}
    """
    # Kiem tra folder ton tai
    voice_dir = VOICE_DATA_DIR / voice_id
    if not voice_dir.exists() or not voice_dir.is_dir():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Voice '{voice_id}' khong ton tai.",
        )

    # Lay ten voice tu meta.json truoc khi xoa
    name = voice_id
    meta_file = voice_dir / "meta.json"
    if meta_file.exists():
        try:
            meta = json.loads(meta_file.read_text())
            name = meta.get("name", voice_id)
        except (json.JSONDecodeError, KeyError):
            pass

    # Xoa folder
    import shutil
    shutil.rmtree(voice_dir)

    # Xoa cache de scan lai
    import app.services.omnivoice_service as svc
    svc._voice_data_cache = None
    svc._voice_data_mtime = 0

    logger.info("Voice da duoc xoa: %s (%s)", voice_id, name)

    return {"message": f"Voice '{name}' da duoc xoa."}
