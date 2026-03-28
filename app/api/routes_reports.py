from fastapi import APIRouter
from app.db.database import get_connection
from app.models.report import ReportCreate, ReportResponse

router = APIRouter(tags=["reports"])


@router.get("/reports")
async def get_reports():
    conn = get_connection()
    rows = conn.execute(
        "SELECT * FROM reports ORDER BY created_at DESC"
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


@router.post("/reports", response_model=ReportResponse)
async def create_report(report: ReportCreate):
    conn = get_connection()
    cursor = conn.execute(
        "INSERT INTO reports (raw_text, source, sender_phone) VALUES (?, ?, ?)",
        (report.text, report.source, report.sender_phone),
    )
    conn.commit()
    row = conn.execute(
        "SELECT * FROM reports WHERE id = ?", (cursor.lastrowid,)
    ).fetchone()
    conn.close()
    return dict(row)


@router.post("/reports/process")
async def process_reports():
    return {"status": "pending", "message": "Field Report Agent not yet connected"}
