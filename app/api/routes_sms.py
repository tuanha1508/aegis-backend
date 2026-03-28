from fastapi import APIRouter, Form
from app.db.database import get_connection

router = APIRouter(tags=["sms"])


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
