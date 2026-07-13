"""
Pydantic schemas cho TTS API - dinh nghia request/response models.
"""

from pydantic import BaseModel, Field
from typing import Optional


class TTSRequest(BaseModel):
    """
    Request body cho TTS generate endpoint.
    """
    text: str = Field(
        ...,
        description="Van ban can chuyen thanh giong noi",
        min_length=1,
    )
    voice_id: Optional[str] = Field(
        None,
        description="ID cua giong doc (vi du: '001'). Neu khong truyen -> su dung voice mac dinh",
    )
    speed: Optional[float] = Field(
        1.0,
        description="Toc do doc (0.5-2.0). Hien tai chua ho tro",
        ge=0.5,
        le=2.0,
    )
    stream: bool = Field(
        False,
        description="Bat streaming mode. True: generate tung chunk, False: generate full",
    )


class TTSResponse(BaseModel):
    """
    Response body cho TTS endpoints.
    """
    task_id: Optional[str] = Field(
        None,
        description="ID cua task TTS (chi co khi goi /generate)",
    )
    status: str = Field(
        ...,
        description="Trang thai xu ly: 'processing', 'success', 'error'",
    )
    lipsync_response: Optional[dict] = Field(
        None,
        description="Phan hoi tu LipSync service (neu co)",
    )
    message: Optional[str] = Field(
        None,
        description="Thong bao chi tiet hoac loi",
    )
