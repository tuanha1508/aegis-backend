from typing import Optional

from fastapi import APIRouter, Query
from pydantic import BaseModel

from app.db.database import get_connection

router = APIRouter(tags=["alerts"])


class AlertGenerateRequest(BaseModel):
    context: Optional[str] = None


@router.get("/alerts")
async def get_alerts(priority: Optional[str] = Query(None)):
    conn = get_connection()
    try:
        if priority:
            rows = conn.execute(
                "SELECT * FROM alerts WHERE priority = %s ORDER BY created_at DESC",
                (priority,),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM alerts ORDER BY created_at DESC"
            ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


@router.post("/alerts/generate")
async def generate_alerts(body: Optional[AlertGenerateRequest] = None):
    """Trigger the Alert Agent to analyze risks/incidents and generate alerts."""
    from app.agents.alert_agent import run_alert_agent

    context = body.context if body else None
    result = await run_alert_agent(context=context)
    return result
