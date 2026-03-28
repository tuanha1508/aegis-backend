from typing import Any, Optional
from uuid import uuid4

from fastapi import APIRouter, Query
from pydantic import BaseModel

from app.db.audit import insert_audit_log
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
    """Trigger the Alert Agent to analyze risks/incidents and generate alerts.

    Optionally pass a context string to guide the agent
    (e.g. \"Focus on Zone A evacuation\" or \"Generate post-storm recovery alerts\").
    """
    run_id = uuid4()
    from app.agents.alert_agent import run_alert_agent

    context = body.context if body else None
    result: Any = await run_alert_agent(context=context)

    conn = get_connection()
    try:
        row = conn.execute("SELECT current_phase FROM phase WHERE id = 1").fetchone()
        phase = row["current_phase"] if row else None
        payload = result if isinstance(result, dict) else {"result": result}
        insert_audit_log(
            conn,
            agent_name="alert_agent",
            run_id=run_id,
            phase=phase,
            input_payload={"trigger": "POST /alerts/generate", "context": context},
            output_payload=payload,
        )
        conn.commit()
    finally:
        conn.close()

    return {**payload, "run_id": str(run_id)}
