from typing import Optional

from fastapi import APIRouter, Form
from pydantic import BaseModel

from app.db.database import get_connection

router = APIRouter(tags=["sms"])

# Keywords that indicate a disaster report vs casual chat
_DISASTER_KEYWORDS = [
    "flood", "water", "surge", "trapped", "stuck", "stranded", "rescue",
    "tree down", "road block", "road closed", "power out", "no power",
    "electricity", "damage", "roof", "collapse", "fire", "smoke", "gas leak",
    "injured", "medical", "hurt", "bleeding", "supply", "blanket", "food",
    "shelter", "evacuate", "tornado", "wind", "storm", "hurricane",
    "missing", "lost", "found", "help", "emergency", "911", "sos",
    "inundacion", "atrapado", "ayuda", "rescate", "dano", "herido",
    "agua", "viento", "techo", "incendio", "familia",
]

_AEGIS_INFO = (
    "I'm Aegis, a disaster response assistant for Tampa Bay. "
    "You can report emergencies to me like:\n"
    "• \"Flooding on Bayshore Blvd, water entering homes\"\n"
    "• \"Family trapped on second floor, Henderson Blvd\"\n"
    "• \"Power out in Seminole Heights\"\n"
    "I'll parse your report, locate it on the map, and alert first responders."
)


def _is_disaster_report(text: str) -> bool:
    """Quick keyword check to classify if a message is a disaster report."""
    lower = text.lower()
    # Very short messages are unlikely to be reports
    if len(lower.split()) < 3:
        return False
    return any(kw in lower for kw in _DISASTER_KEYWORDS)


class SmsChatRequest(BaseModel):
    message: str
    phone: Optional[str] = None
    lat: Optional[float] = None
    lng: Optional[float] = None


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
    """SMS chat simulator — classifies the message first.

    If it's a disaster report → stores it, runs Field Report Agent, returns parsed data.
    If it's casual chat → replies with info about Aegis without creating a report.
    """
    # Classify: is this a disaster report or casual chat?
    if not _is_disaster_report(body.message):
        return {
            "status": "success",
            "reply": _AEGIS_INFO,
            "report": None,
            "report_id": None,
            "is_report": False,
        }

    # It's a disaster report — store and process
    from app.agents.field_report_agent import run_field_report_agent_single

    # If GPS coords provided, store them directly on the report
    conn = get_connection()
    try:
        if body.lat is not None and body.lng is not None:
            row = conn.execute(
                """INSERT INTO reports (raw_text, source, sender_phone, lat, lng)
                   VALUES (%s, 'sms_chat', %s, %s, %s) RETURNING id""",
                (body.message, body.phone, body.lat, body.lng),
            ).fetchone()
        else:
            row = conn.execute(
                """INSERT INTO reports (raw_text, source, sender_phone)
                   VALUES (%s, 'sms_chat', %s) RETURNING id""",
                (body.message, body.phone),
            ).fetchone()
        conn.commit()
        report_id = row["id"]
    finally:
        conn.close()

    result = await run_field_report_agent_single(
        report_id, body.message, user_lat=body.lat, user_lng=body.lng
    )

    # Auto-cascade: trigger severity + alert pipeline in background
    # Don't block the user response — run async
    if result.get("status") == "success":
        from app.services.agent_pipeline import auto_cascade_report
        import asyncio
        asyncio.create_task(auto_cascade_report(report_id))

    return {
        "status": result.get("status", "error"),
        "reply": result.get("reply", "Unable to process your report at this time."),
        "report": result.get("report"),
        "report_id": report_id,
        "is_report": True,
    }
