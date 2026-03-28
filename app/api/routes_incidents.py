from fastapi import APIRouter, Query
from typing import Optional
from app.db.database import get_connection

router = APIRouter(tags=["incidents"])


@router.get("/incidents")
async def get_incidents(severity: Optional[str] = Query(None)):
    conn = get_connection()
    if severity:
        rows = conn.execute(
            "SELECT * FROM incidents WHERE severity_label = ? ORDER BY severity_score DESC",
            (severity,),
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT * FROM incidents ORDER BY severity_score DESC"
        ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


@router.post("/incidents/rank")
async def rank_incidents():
    return {"status": "pending", "message": "Severity Agent not yet connected"}
