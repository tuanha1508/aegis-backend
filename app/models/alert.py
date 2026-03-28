from pydantic import BaseModel
from datetime import datetime
from typing import Optional


class AlertResponse(BaseModel):
    id: int
    phase: str
    priority: str
    neighborhood: Optional[str] = None
    title: str
    message: str
    message_es: Optional[str] = None
    channels: Optional[str] = None
    delivered: bool = False
    created_at: Optional[datetime] = None
