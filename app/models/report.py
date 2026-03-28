from pydantic import BaseModel
from datetime import datetime
from typing import Optional


class ReportCreate(BaseModel):
    text: str
    source: str = "app"
    sender_phone: Optional[str] = None


class ReportResponse(BaseModel):
    id: int
    raw_text: str
    source: str
    sender_phone: Optional[str] = None
    location_text: Optional[str] = None
    lat: Optional[float] = None
    lng: Optional[float] = None
    incident_type: Optional[str] = None
    people_mentioned: Optional[int] = None
    has_children: bool = False
    language: str = "en"
    processed: bool = False
    created_at: Optional[datetime] = None
