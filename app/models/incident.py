from pydantic import BaseModel
from datetime import datetime
from typing import Optional


class IncidentResponse(BaseModel):
    id: int
    report_ids: Optional[str] = None
    incident_type: str
    location_text: Optional[str] = None
    lat: float
    lng: float
    severity_score: Optional[int] = None
    severity_label: Optional[str] = None
    factors: Optional[str] = None
    recommended_action: Optional[str] = None
    verified: bool = False
    report_count: int = 1
    resolved: bool = False
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
