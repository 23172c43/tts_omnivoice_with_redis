from pydantic import BaseModel, Field
from typing import Optional

class TTSRequest(BaseModel):
    text: str = Field(..., description="Van ban can chuyen thanh giong noi", min_length = 1)
    voice_id: Optional[str] = Field(None, description="ID cua giong doc (neu co)")
    speed: Optional[float] = Field(1.0, description="Toc do doc (0.5 - 2.0)", ge = 0.5, le=2.0)


class TTSResponse(BaseModel):
    task_id: str = Field(..., description="ID cua task TTS")
    status: str = Field(..., description="Trang thai xu ly (success/error/processing)")
    audio_url: Optional[str] = Field(None, description="Duong dan den file am thanh")
    message: Optional[str] = Field(None, description="Thong bao loi hoac chi tiet them")

