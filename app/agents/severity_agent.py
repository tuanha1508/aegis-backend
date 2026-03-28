"""
Severity Agent — Scores and ranks disaster incidents by urgency.

Uses Google ADK + Gemini to analyze processed field reports, score urgency
0-100, consolidate duplicate reports, and produce ranked incident lists
with recommended actions. Results are persisted to the incidents table.
"""

from __future__ import annotations

import json
import logging
import os
import uuid
from typing import Any

from google.adk.agents import Agent
from google.adk.models.lite_llm import LiteLlm
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.genai import types

from app.config import GEMINI_API_KEY, GROQ_API_KEY
from app.db.database import get_connection

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# ADK Tool Functions
# ---------------------------------------------------------------------------


def get_processed_reports() -> dict:
    """Fetch all processed field reports that haven't been assigned to incidents yet.

    Returns:
        dict: List of processed reports with their parsed fields including
              location, incident type, people count, and coordinates.
    """
    conn = get_connection()
    try:
        rows = conn.execute(
            """SELECT * FROM reports
               WHERE processed = 1
               ORDER BY created_at ASC"""
        ).fetchall()
    finally:
        conn.close()

    if not rows:
        return {"status": "no_data", "reports": []}

    return {"status": "ok", "count": len(rows), "reports": [dict(r) for r in rows]}


def get_existing_incidents() -> dict:
    """Fetch all existing unresolved incidents from the database.

    Use this to check for duplicate or related reports that should be
    consolidated into existing incidents rather than creating new ones.

    Returns:
        dict: List of current incidents with their types, locations, and severity.
    """
    conn = get_connection()
    try:
        rows = conn.execute(
            "SELECT * FROM incidents WHERE resolved = 0 ORDER BY severity_score DESC"
        ).fetchall()
    finally:
        conn.close()

    if not rows:
        return {"status": "no_incidents", "incidents": []}

    return {"status": "ok", "count": len(rows), "incidents": [dict(r) for r in rows]}


def get_resources() -> dict:
    """Fetch all available resources (shelters, medical, supplies).

    Use this to factor resource proximity into severity scoring —
    incidents far from resources should get higher severity scores.

    Returns:
        dict: List of resources with their type, location, capacity, and status.
    """
    conn = get_connection()
    try:
        rows = conn.execute(
            "SELECT * FROM resources WHERE status = 'open' ORDER BY type"
        ).fetchall()
    finally:
        conn.close()

    if not rows:
        return {"status": "no_resources", "resources": []}

    return {"status": "ok", "count": len(rows), "resources": [dict(r) for r in rows]}


def save_incident(
    report_ids: str,
    incident_type: str,
    location_text: str,
    lat: float,
    lng: float,
    severity_score: int,
    severity_label: str,
    factors: str,
    recommended_action: str,
    report_count: int,
) -> dict:
    """Save a new incident or update an existing one in the database.

    Args:
        report_ids: Comma-separated list of report IDs that make up this incident.
        incident_type: Type of incident (e.g. 'flooding', 'trapped_person').
        location_text: Human-readable location description.
        lat: Latitude of the incident location.
        lng: Longitude of the incident location.
        severity_score: Urgency score from 0-100 (100 = most urgent).
        severity_label: One of 'critical' (75-100), 'high' (50-74),
                        'medium' (25-49), 'low' (0-24).
        factors: JSON string listing factors that contributed to the score.
                 e.g. '["life_threat", "children_present", "no_nearby_shelter"]'
        recommended_action: Recommended emergency response action.
        report_count: Number of reports consolidated into this incident.

    Returns:
        dict: Status and the saved incident ID.
    """
    conn = get_connection()
    try:
        row = conn.execute(
            """INSERT INTO incidents
               (report_ids, incident_type, location_text, lat, lng,
                severity_score, severity_label, factors, recommended_action,
                report_count)
               VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s) RETURNING id""",
            (
                report_ids, incident_type, location_text, lat, lng,
                severity_score, severity_label, factors, recommended_action,
                report_count,
            ),
        ).fetchone()
        conn.commit()
        incident_id = row["id"]
    finally:
        conn.close()

    return {"status": "saved", "incident_id": incident_id}


# ---------------------------------------------------------------------------
# Agent Definition
# ---------------------------------------------------------------------------

SEVERITY_INSTRUCTION = """\
You are the Aegis Severity Agent for Tampa Bay disaster response.

Your job is to analyze processed field reports, score their urgency, consolidate
duplicate reports into single incidents, and produce a ranked incident list
with recommended emergency response actions.

## Your Workflow

1. Call `get_processed_reports()` to get all processed field reports.
2. Call `get_existing_incidents()` to see if any incidents already exist.
3. Call `get_resources()` to know where shelters and supplies are located.
4. Analyze the reports and:
   a. Group related reports (same incident type + nearby location) together.
   b. Score each incident's urgency from 0-100.
   c. Assign a severity label based on score.
   d. List the factors that justify the score.
   e. Recommend a specific emergency response action.
5. Call `save_incident()` for each distinct incident.
6. Provide a ranked summary of all incidents.

## Severity Scoring Criteria (0-100)

### Life Threat (+30-40 points)
- Trapped persons: +40
- Medical emergency: +35
- Structural collapse with people: +40
- Rising water with people present: +35

### Vulnerable Populations (+10-20 points)
- Children present: +20
- Elderly present: +15
- Disabled persons: +15

### Scale & Impact (+5-15 points)
- Multiple people affected (4+): +10
- Multiple reports for same incident: +5 per additional report
- Critical infrastructure affected: +15

### Resource Proximity (-5 to +15 points)
- No shelter within 3 miles: +15
- No medical within 5 miles: +10
- Resources nearby and available: -5

### Escalation Factors (+5-10 points)
- Situation worsening (water rising, fire spreading): +10
- No access route available: +10
- Night time incident: +5

## Severity Labels
- **critical** (75-100): Immediate life threat, deploy rescue
- **high** (50-74): Urgent, needs response within 1 hour
- **medium** (25-49): Important, needs response within 4 hours
- **low** (0-24): Monitor, respond when resources available

## Consolidation Rules
- Reports about the same location AND same incident type → merge into one incident
- Track all contributing report_ids as a comma-separated string
- Use the average coordinates of merged reports
- Score reflects the worst-case from merged reports

## CRITICAL RULES
- Create an incident for EVERY processed report (either new or merged).
- The report_ids field must contain the actual database IDs of the reports.
- factors must be a valid JSON array of strings.
- After saving all incidents, provide a ranked summary from most to least urgent.
"""


def _get_model():
    """Pick the best available model — Groq if key exists, else Gemini."""
    if GROQ_API_KEY:
        return LiteLlm(model="groq/llama-3.3-70b-versatile")
    return "gemini-2.0-flash"


def _build_severity_agent() -> Agent:
    """Create a fresh Severity Agent instance."""
    return Agent(
        name="severity_agent",
        model=_get_model(),
        description=(
            "Analyzes processed field reports to score urgency, consolidate "
            "duplicates, and produce ranked incident lists with severity scores "
            "and recommended emergency response actions."
        ),
        instruction=SEVERITY_INSTRUCTION,
        tools=[get_processed_reports, get_existing_incidents, get_resources, save_incident],
    )


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------

APP_NAME = "aegis"


async def run_severity_agent() -> dict[str, Any]:
    """Execute the Severity Agent to rank all processed reports into incidents.

    Returns a dict with:
        - status: "success" or "error"
        - summary: text summary from the agent
        - incidents: list of incidents from the DB
    """
    if GROQ_API_KEY:
        os.environ.setdefault("GROQ_API_KEY", GROQ_API_KEY)
    if GEMINI_API_KEY:
        os.environ.setdefault("GOOGLE_API_KEY", GEMINI_API_KEY)

    agent = _build_severity_agent()
    session_service = InMemorySessionService()
    runner = Runner(
        agent=agent,
        app_name=APP_NAME,
        session_service=session_service,
    )

    user_id = "aegis_system"
    session_id = f"severity_{uuid.uuid4().hex[:8]}"

    session = await session_service.create_session(
        app_name=APP_NAME,
        user_id=user_id,
        session_id=session_id,
    )

    user_message = types.Content(
        role="user",
        parts=[types.Part(text=(
            "Analyze all processed field reports. Score urgency, consolidate "
            "duplicates, and save ranked incidents with severity scores and "
            "recommended actions. Consider resource proximity in your scoring."
        ))],
    )

    final_text = ""
    try:
        async for event in runner.run_async(
            user_id=user_id,
            session_id=session.id,
            new_message=user_message,
        ):
            if event.is_final_response() and event.content and event.content.parts:
                final_text = event.content.parts[0].text
    except Exception as e:
        logger.error("Severity Agent error: %s", e)
        return {"status": "error", "error": str(e), "incidents": []}

    # Fetch the incidents from DB
    conn = get_connection()
    try:
        rows = conn.execute(
            "SELECT * FROM incidents ORDER BY severity_score DESC"
        ).fetchall()
    finally:
        conn.close()

    incidents = [dict(r) for r in rows]

    return {
        "status": "success",
        "summary": final_text,
        "incidents": incidents,
        "incidents_count": len(incidents),
    }
