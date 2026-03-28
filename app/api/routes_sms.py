from fastapi import APIRouter, Form
from app.db.database import get_connection

router = APIRouter(tags=["sms"])


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
