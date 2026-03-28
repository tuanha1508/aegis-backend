from typing import Any, Optional
from uuid import uuid4

from fastapi import APIRouter, Query

from app.db.audit import insert_audit_log
from app.db.database import get_connection

router = APIRouter(tags=["incidents"])


@router.get("/incidents")
async def get_incidents(severity: Optional[str] = Query(None)):
    conn = get_connection()
    try:
        if severity:
            rows = conn.execute(
                """SELECT * FROM incidents WHERE severity_label = %s
                   ORDER BY severity_score DESC NULLS LAST""",
                (severity,),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM incidents ORDER BY severity_score DESC NULLS LAST"
            ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


@router.post("/incidents/rank")
async def rank_incidents():
    """Trigger the Severity Agent to score and rank processed reports into incidents."""
    run_id = uuid4()
    from app.agents.severity_agent import run_severity_agent

    result: Any = await run_severity_agent()

    conn = get_connection()
    try:
        row = conn.execute("SELECT current_phase FROM phase WHERE id = 1").fetchone()
        phase = row["current_phase"] if row else None
        payload = result if isinstance(result, dict) else {"result": result}
        insert_audit_log(
            conn,
            agent_name="severity_agent",
            run_id=run_id,
            phase=phase,
            input_payload={"trigger": "POST /incidents/rank"},
            output_payload=payload,
        )
        conn.commit()
    finally:
        conn.close()

    return {**payload, "run_id": str(run_id)}
