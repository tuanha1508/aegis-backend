from fastapi import APIRouter, Query
from typing import Optional
from app.db.database import get_connection

router = APIRouter(tags=["alerts"])


@router.get("/alerts")
async def get_alerts(priority: Optional[str] = Query(None)):
    conn = get_connection()
    if priority:
        rows = conn.execute(
            "SELECT * FROM alerts WHERE priority = ? ORDER BY created_at DESC",
            (priority,),
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT * FROM alerts ORDER BY created_at DESC"
        ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


@router.post("/alerts/generate")
async def generate_alerts():
    return {"status": "pending", "message": "Alert Agent not yet connected"}
