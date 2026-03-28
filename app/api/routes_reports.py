from fastapi import APIRouter

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
    """Trigger the Field Report Agent to batch-process all unprocessed reports."""
    from app.agents.field_report_agent import run_field_report_agent

    result = await run_field_report_agent()
    return result
