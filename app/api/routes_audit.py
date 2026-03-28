from typing import List, Optional

from fastapi import APIRouter, Query

from app.db.database import get_connection
from app.models.audit_log import AuditLogEntry

router = APIRouter(tags=["audit"])


@router.get("/audit-log", response_model=List[AuditLogEntry])
async def list_audit_log(
    run_id: Optional[str] = Query(None, description="Filter by orchestration run UUID"),
    limit: int = Query(100, ge=1, le=500),
):
    conn = get_connection()
    try:
        if run_id:
            rows = conn.execute(
                """SELECT * FROM audit_log WHERE run_id = %s::uuid
                   ORDER BY created_at DESC LIMIT %s""",
                (run_id, limit),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM audit_log ORDER BY created_at DESC LIMIT %s",
                (limit,),
            ).fetchall()
        return [AuditLogEntry.model_validate(dict(r)) for r in rows]
    finally:
        conn.close()
