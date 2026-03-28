from pydantic import BaseModel
from datetime import datetime
from typing import Optional


class PhaseResponse(BaseModel):
    current_phase: str
    started_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


class PhaseSetRequest(BaseModel):
    phase: str
