from pydantic import BaseModel
from datetime import datetime
from typing import Optional


class MissingPersonCreate(BaseModel):
    reported_by: str
    reporter_phone: Optional[str] = None
    name: str
    age: Optional[int] = None
    gender: Optional[str] = None
    description: Optional[str] = None
    last_known_location: Optional[str] = None
    last_known_lat: Optional[float] = None
    last_known_lng: Optional[float] = None
    last_contact: Optional[datetime] = None


class MissingPersonResponse(BaseModel):
    id: int
    reported_by: str
    reporter_phone: Optional[str] = None
    name: str
    age: Optional[int] = None
    gender: Optional[str] = None
    description: Optional[str] = None
    last_known_location: Optional[str] = None
    last_known_lat: Optional[float] = None
    last_known_lng: Optional[float] = None
    last_contact: Optional[datetime] = None
    status: str = "missing"
    created_at: Optional[datetime] = None


class FoundPersonCreate(BaseModel):
    name: str
    age_approx: Optional[int] = None
    gender: Optional[str] = None
    description: Optional[str] = None
    found_at: Optional[str] = None
    found_lat: Optional[float] = None
    found_lng: Optional[float] = None


class FoundPersonResponse(BaseModel):
    id: int
    name: str
    age_approx: Optional[int] = None
    gender: Optional[str] = None
    description: Optional[str] = None
    found_at: Optional[str] = None
    found_lat: Optional[float] = None
    found_lng: Optional[float] = None
    checked_in: Optional[datetime] = None
    matched_missing_id: Optional[int] = None


class MatchResponse(BaseModel):
    id: int
    missing_id: int
    found_id: int
    confidence: float
    match_factors: Optional[str] = None
    status: str = "pending"
    reviewed_by: Optional[str] = None
    created_at: Optional[datetime] = None
