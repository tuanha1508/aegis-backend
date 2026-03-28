from uuid import uuid4

from fastapi import APIRouter

from app.db.audit import insert_audit_log
from app.db.database import get_connection
from app.models.report import ReportCreate, ReportResponse

router = APIRouter(tags=["reports"])


@router.get("/reports")
async def get_reports():
    conn = get_connection()
    try:
        rows = conn.execute(
            "SELECT * FROM reports ORDER BY created_at DESC"
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


@router.post("/reports", response_model=ReportResponse)
async def create_report(report: ReportCreate):
    conn = get_connection()
    try:
        row = conn.execute(
            """INSERT INTO reports (raw_text, source, sender_phone)
               VALUES (%s, %s, %s) RETURNING *""",
            (report.text, report.source, report.sender_phone),
        ).fetchone()
        conn.commit()
        return dict(row)
    finally:
        conn.close()


@router.post("/reports/process")
async def process_reports():
    run_id = uuid4()
    conn = get_connection()
    try:
        row = conn.execute("SELECT current_phase FROM phase WHERE id = 1").fetchone()
        phase = row["current_phase"] if row else None
        insert_audit_log(
            conn,
            agent_name="field_report_agent",
            run_id=run_id,
            phase=phase,
            input_payload={"trigger": "POST /reports/process"},
            output_payload={
                "status": "pending",
                "message": "Field Report Agent not yet connected",
            },
        )
        conn.commit()
    finally:
        conn.close()
    return {
        "status": "pending",
        "message": "Field Report Agent not yet connected",
        "run_id": str(run_id),
    }
