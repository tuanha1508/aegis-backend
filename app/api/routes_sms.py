from fastapi import APIRouter, Form
from pydantic import BaseModel
from typing import Optional

from app.db.database import get_connection

router = APIRouter(tags=["sms"])


class SmsChatRequest(BaseModel):
    message: str
    phone: Optional[str] = None


@router.post("/sms/webhook")
async def sms_webhook(From: str = Form(...), Body: str = Form(...)):
    conn = get_connection()
    conn.execute(
        "INSERT INTO reports (raw_text, source, sender_phone) VALUES (?, 'sms', ?)",
        (Body, From),
    )
    conn.commit()
    conn.close()
    return {"status": "received"}


@router.post("/sms/chat")
async def sms_chat(body: SmsChatRequest):
    """SMS chat simulator — accepts a message, stores it as a report,
    runs the Field Report Agent to parse it, and returns an AI reply.

    This replaces real Twilio SMS for the demo since US carriers block
    unverified numbers.
    """
    from app.agents.field_report_agent import run_field_report_agent_single

    # Store the message as an unprocessed report
    conn = get_connection()
    cursor = conn.execute(
        "INSERT INTO reports (raw_text, source, sender_phone) VALUES (?, 'sms_chat', ?)",
        (body.message, body.phone),
    )
    conn.commit()
    report_id = cursor.lastrowid
    conn.close()

    # Run the Field Report Agent on this single report
    result = await run_field_report_agent_single(report_id, body.message)

    return {
        "status": result.get("status", "error"),
        "reply": result.get("reply", "Unable to process your report at this time."),
        "report": result.get("report"),
        "report_id": report_id,
    }
