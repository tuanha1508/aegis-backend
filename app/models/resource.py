from pydantic import BaseModel
from datetime import datetime
from typing import Optional


class ResourceResponse(BaseModel):
    id: int
    type: str
    name: str
    lat: float
    lng: float
    address: Optional[str] = None
    capacity: Optional[int] = None
    current_occupancy: Optional[int] = None
    amenities: Optional[str] = None
    status: str = "open"
    notes: Optional[str] = None
    last_updated: Optional[datetime] = None


class ResourceUpdate(BaseModel):
    status: Optional[str] = None
    current_occupancy: Optional[int] = None
    notes: Optional[str] = None
