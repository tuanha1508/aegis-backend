from typing import Optional

from fastapi import APIRouter, Form
from pydantic import BaseModel

from app.db.database import get_connection

router = APIRouter(tags=["sms"])


class SmsChatRequest(BaseModel):
    message: str
    phone: Optional[str] = None


@router.post("/sms/webhook")
async def sms_webhook(From: str = Form(...), Body: str = Form(...)):
    conn = get_connection()
    try:
        conn.execute(
            """INSERT INTO reports (raw_text, source, sender_phone)
               VALUES (%s, 'sms', %s)""",
            (Body, From),
        )
        conn.commit()
        return {"status": "received"}
    finally:
        conn.close()


@router.post("/sms/chat")
async def sms_chat(body: SmsChatRequest):
    """SMS chat simulator — accepts a message, stores it as a report,
    runs the Field Report Agent to parse it, and returns an AI reply.
    """
    from app.agents.field_report_agent import run_field_report_agent_single

    conn = get_connection()
    try:
        row = conn.execute(
            """INSERT INTO reports (raw_text, source, sender_phone)
               VALUES (%s, 'sms_chat', %s) RETURNING id""",
            (body.message, body.phone),
        ).fetchone()
        conn.commit()
        report_id = row["id"]
    finally:
        conn.close()

    result = await run_field_report_agent_single(report_id, body.message)

    return {
        "status": result.get("status", "error"),
        "reply": result.get("reply", "Unable to process your report at this time."),
        "report": result.get("report"),
        "report_id": report_id,
    }
