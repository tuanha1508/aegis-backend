from datetime import datetime
from typing import Any, Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, field_serializer


class AuditLogEntry(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    agent_name: str
    run_id: UUID
    phase: Optional[str] = None
    input_payload: Optional[dict[str, Any]] = None
    output_payload: Optional[dict[str, Any]] = None
    error_message: Optional[str] = None
    duration_ms: Optional[int] = None
    related_report_id: Optional[int] = None
    related_incident_id: Optional[int] = None
    related_assignment_id: Optional[int] = None
    created_at: Optional[datetime] = None

    @field_serializer("run_id")
    def serialize_run_id(self, v: UUID) -> str:
        return str(v)
