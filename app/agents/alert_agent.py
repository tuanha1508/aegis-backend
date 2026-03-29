"""
Alert Agent — Generates multilingual disaster alerts for Tampa Bay.

Takes risk data from Monitor Agent OR incident data from Severity Agent,
uses Gemini to craft plain-language warnings in English and Spanish,
determines priority level, and delivers via Twilio SMS.
"""

import logging
import os
import uuid
from datetime import datetime

from google.adk.agents import Agent
from google.adk.models.lite_llm import LiteLlm
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.genai import types

from app.config import GEMINI_API_KEY, GROQ_API_KEY
from app.db.database import get_connection
from app.services.twilio_service import send_sms

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# ADK Tool Functions
# ---------------------------------------------------------------------------
# Google ADK tools are plain Python functions with docstrings.  The agent
# will decide when to call them based on its instruction.
# ---------------------------------------------------------------------------


def get_risk_data() -> dict:
    """Fetch current neighborhood risk assessments from the database.

    Returns a JSON object containing all risk assessments including
    neighborhood names, flood risk scores, storm surge estimates,
    evacuation recommendations, and time-to-impact estimates.
    Use this to understand which areas are most at risk before generating alerts.
    """
    conn = get_connection()
    rows = conn.execute(
        "SELECT * FROM risk_assessments ORDER BY flood_risk DESC"
    ).fetchall()
    conn.close()

    if not rows:
        return {"status": "no_data", "assessments": []}

    assessments = [dict(r) for r in rows]
    return {"status": "ok", "count": len(assessments), "assessments": assessments}


def get_current_phase() -> dict:
    """Fetch the current disaster phase from the database.

    Returns 'pre_storm', 'active_storm', or 'post_storm'.
    The phase determines the tone and urgency of alerts:
    - pre_storm: focus on evacuation warnings and preparation
    - active_storm: focus on immediate safety and shelter-in-place
    - post_storm: focus on recovery resources and reunification
    """
    conn = get_connection()
    row = conn.execute("SELECT current_phase FROM phase WHERE id = 1").fetchone()
    conn.close()

    phase = row["current_phase"] if row else "pre_storm"
    return {"phase": phase}


def get_active_incidents() -> dict:
    """Fetch unresolved incidents ranked by severity from the database.

    Returns incidents with their severity scores, types, locations,
    and recommended actions. Use this during active_storm phase to
    generate alerts about ongoing emergencies.
    """
    conn = get_connection()
    try:
        rows = conn.execute(
            """SELECT * FROM incidents WHERE resolved = false
               ORDER BY severity_score DESC NULLS LAST"""
        ).fetchall()
    finally:
        conn.close()

    if not rows:
        return {"status": "no_incidents", "incidents": []}

    incidents = [dict(r) for r in rows]
    return {"status": "ok", "count": len(incidents), "incidents": incidents}


def save_alert(
    phase: str,
    priority: str,
    neighborhood: str,
    title: str,
    message: str,
    message_es: str,
    channels: str,
) -> dict:
    """Save a generated alert to the database.

    Args:
        phase: Current disaster phase ('pre_storm', 'active_storm', or 'post_storm')
        priority: Alert priority level — must be one of: 'info', 'warning', 'critical', 'emergency'
        neighborhood: Target neighborhood name (e.g. 'Davis Islands', 'Palma Ceia') or 'all' for citywide
        title: Short alert title (under 80 chars)
        message: Full alert message in English
        message_es: Full alert message in Spanish
        channels: Comma-separated delivery channels used (e.g. 'sms,voice,app')

    Returns the saved alert ID.
    """
    conn = get_connection()
    try:
        row = conn.execute(
            """INSERT INTO alerts (phase, priority, neighborhood, title, message, message_es, channels, delivered)
               VALUES (%s, %s, %s, %s, %s, %s, %s, TRUE) RETURNING id""",
            (phase, priority, neighborhood, title, message, message_es, channels),
        ).fetchone()
        conn.commit()
        alert_id = row["id"] if row else None
    finally:
        conn.close()

    return {"status": "saved", "alert_id": alert_id}


def send_sms_alert(phone_number: str, message: str) -> dict:
    """Send an SMS alert to a specific phone number via Twilio.

    Args:
        phone_number: Recipient phone number in E.164 format (e.g. '+18135551234')
        message: The alert text to send (max 1600 chars for SMS)

    Returns delivery status from Twilio.
    """
    result = send_sms(to=phone_number, body=message)
    return result



# ---------------------------------------------------------------------------
# Agent Definition
# ---------------------------------------------------------------------------

ALERT_AGENT_INSTRUCTION = """You are the Aegis Alert Agent for Tampa Bay disaster response.

Your job is to analyze risk data and incidents, then generate clear, actionable emergency alerts
for Tampa Bay residents. You operate across all disaster phases.

## Your Workflow

1. ALWAYS start by calling `get_current_phase()` to know which disaster phase we are in.
2. Call `get_risk_data()` to see neighborhood risk assessments.
3. Call `get_active_incidents()` to see any ongoing emergencies.
4. Based on the data, generate alerts following the rules below.
5. Save EACH alert using `save_alert()`.


## Alert Priority Rules

- **emergency**: Life-threatening situations — trapped people, rapidly rising water, structural collapse.
  Immediate evacuation or shelter-in-place required.
- **critical**: High flood risk (>0.7), storm surge >6ft, incidents with severity_score >75.
  Evacuate now or take immediate protective action.
- **warning**: Moderate risk (0.4-0.7), storm surge 3-6ft, incidents with severity_score 40-75.
  Prepare to evacuate or take precautions.
- **info**: Low risk (<0.4), general updates, resource availability, phase transitions.

## Phase-Specific Behavior

- **pre_storm**: Focus on evacuation warnings for high-risk zones. Include evacuation deadlines,
  shelter locations, and preparation steps. Emphasize Zone A neighborhoods first.
- **active_storm**: Focus on immediate safety. Alert about ongoing incidents, shelter-in-place
  instructions, rescue operations, and road closures.
- **post_storm**: Focus on recovery — where to find resources, shelter status, power/water
  restoration updates, reunification information.

## Message Format Rules

- Title: Short and urgent (under 80 characters)
- English message: 2-4 sentences. Lead with the most critical action. Include specific locations.
- Spanish message: Accurate translation of the English message. Use clear, standard Spanish.
- Always mention specific Tampa Bay neighborhoods and landmarks.
- Include concrete numbers (flood risk %, storm surge feet, time to impact).

## Channel Selection

- info → channels: "app"
- warning → channels: "app,sms"
- critical → channels: "app,sms,voice"
- emergency → channels: "app,sms,voice"

## Important

- Generate ONE alert per affected neighborhood for critical/emergency.
- For warning/info, you can group multiple neighborhoods into one alert.
- If there is no risk data and no incidents, generate a single info-level "all clear" update.
- After saving all alerts, provide a summary of what you generated.
"""

def _get_model():
    """Pick the best available model — Groq if key exists, else Gemini."""
    if GROQ_API_KEY:
        return LiteLlm(model="groq/llama-3.3-70b-versatile")
    return "gemini-2.0-flash"


def _build_alert_agent() -> Agent:
    """Create a fresh Alert Agent instance."""
    return Agent(
        name="alert_agent",
        model=_get_model(),
        description="Generates multilingual disaster alerts based on risk assessments and active incidents for Tampa Bay neighborhoods.",
        instruction=ALERT_AGENT_INSTRUCTION,
        tools=[
            get_risk_data,
            get_current_phase,
            get_active_incidents,
            save_alert,
            send_sms_alert,
        ],
    )


# ---------------------------------------------------------------------------
# Runner — call run_alert_agent() from the API route
# ---------------------------------------------------------------------------

APP_NAME = "aegis"


async def run_alert_agent(context: str | None = None) -> dict:
    """Execute the Alert Agent and return the generated alerts.

    Args:
        context: Optional additional context to include in the prompt
                 (e.g. "Focus on Davis Islands evacuation" or incident data).

    Returns a dict with the agent's summary and list of generated alert IDs.
    """
    if GROQ_API_KEY:
        os.environ.setdefault("GROQ_API_KEY", GROQ_API_KEY)
    if GEMINI_API_KEY:
        os.environ.setdefault("GOOGLE_API_KEY", GEMINI_API_KEY)

    agent = _build_alert_agent()
    session_service = InMemorySessionService()
    runner = Runner(
        agent=agent,
        app_name=APP_NAME,
        session_service=session_service,
    )

    user_id = "aegis_system"
    session_id = f"alert_{uuid.uuid4().hex[:8]}"

    session = await session_service.create_session(
        app_name=APP_NAME,
        user_id=user_id,
        session_id=session_id,
    )

    # Build the user message
    prompt = "Analyze current risk data and incidents, then generate appropriate alerts for Tampa Bay."
    if context:
        prompt += f"\n\nAdditional context: {context}"

    user_message = types.Content(
        role="user",
        parts=[types.Part(text=prompt)],
    )

    # Run the agent and collect the final response
    final_text = ""

    try:
        async for event in runner.run_async(
            user_id=user_id,
            session_id=session_id,
            new_message=user_message,
        ):
            # Collect tool call info for the response
            if event.actions and event.actions.escalate:
                logger.warning("Alert agent escalated: %s", event.actions.escalate)

            if event.is_final_response() and event.content and event.content.parts:
                final_text = event.content.parts[0].text
    except Exception as e:
        logger.error("Alert agent error: %s", e)
        return {
            "status": "error",
            "error": str(e),
            "alerts_generated": 0,
        }

    # Fetch alerts that were just created
    conn = get_connection()
    try:
        rows = conn.execute(
            """SELECT id, phase, priority, neighborhood, title, channels, created_at
               FROM alerts
               ORDER BY created_at DESC
               LIMIT 20"""
        ).fetchall()
    finally:
        conn.close()

    recent_alerts = []
    for r in rows:
        d = dict(r)
        if d.get("created_at"):
            d["created_at"] = str(d["created_at"])
        recent_alerts.append(d)

    return {
        "status": "success",
        "agent_summary": final_text,
        "alerts": recent_alerts,
        "alerts_generated": len(recent_alerts),
    }
