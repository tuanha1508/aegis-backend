from datetime import datetime
from typing import Optional

from pydantic import BaseModel


class AssignmentCreate(BaseModel):
    incident_id: int
    recommended_action: Optional[str] = None
    assignee: Optional[str] = None
    notes: Optional[str] = None


class AssignmentStatusUpdate(BaseModel):
    status: str
    assignee: Optional[str] = None
    notes: Optional[str] = None


class AssignmentResponse(BaseModel):
    id: int
    incident_id: int
    recommended_action: Optional[str] = None
    assignee: Optional[str] = None
    status: str = "pending"
    assigned_at: Optional[datetime] = None
    accepted_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    notes: Optional[str] = None
