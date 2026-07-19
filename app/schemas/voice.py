"""
Pydantic schemas cho Voice management endpoints.
"""

from pydantic import BaseModel, Field
from typing import Optional


class VoiceInfo(BaseModel):
    """Thong tin 1 voice."""
    voice_id: str = Field(..., description="ID cua voice (vi du: '001')")
    name: str = Field(..., description="Ten de goi (vi du: 'Giọng Tô Vĩnh Diện')")
    ref_text: str = Field(..., description="Van ban mau cua voice")


class VoiceUploadResponse(BaseModel):
    """Response khi upload voice thanh cong."""
    voice_id: str = Field(..., description="Voice ID vua tao")
    name: str = Field(..., description="Ten voice")
    message: str = Field(..., description="Thong bao ket qua")
