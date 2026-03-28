from typing import Optional
from uuid import uuid4

from fastapi import APIRouter, Query

from app.db.audit import insert_audit_log
from app.db.database import get_connection

router = APIRouter(tags=["alerts"])


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
async def generate_alerts():
    run_id = uuid4()
    conn = get_connection()
    try:
        row = conn.execute("SELECT current_phase FROM phase WHERE id = 1").fetchone()
        phase = row["current_phase"] if row else None
        insert_audit_log(
            conn,
            agent_name="alert_agent",
            run_id=run_id,
            phase=phase,
            input_payload={"trigger": "POST /alerts/generate"},
            output_payload={
                "status": "pending",
                "message": "Alert Agent not yet connected",
            },
        )
        conn.commit()
    finally:
        conn.close()
    return {
        "status": "pending",
        "message": "Alert Agent not yet connected",
        "run_id": str(run_id),
    }
