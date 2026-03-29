from pydantic import BaseModel, Field
from datetime import datetime
from typing import Optional


class ResourcePlanRequest(BaseModel):
    lat: float
    lng: float
    needs: list[str] = Field(
        ...,
        description="One or more of: shelter, medical, supply_point, charging, road",
    )
    max_miles: float = Field(default=25.0, ge=0.5, le=200.0)


class ResourcePlanResponse(BaseModel):
    origin: dict
    max_miles: float
    needs: list[str]
    recommendations: list[dict]
    narrative: Optional[str] = None


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
