"""
Monitor Agent — Pre-storm risk assessment for Tampa Bay neighborhoods.

Uses Google ADK + Gemini Flash to analyze NOAA weather data and Tampa
evacuation zones, then produces per-neighborhood flood risk scores and
evacuation recommendations.  Results are persisted to the risk_assessments
table in PostgreSQL (Supabase).
"""

from __future__ import annotations

import json
import logging
import os
import uuid
from pathlib import Path
from typing import Any

from google.adk.agents import Agent
from google.adk.models.lite_llm import LiteLlm
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.genai import types

from app.config import GEMINI_API_KEY, GROQ_API_KEY
from app.db.database import get_connection

logger = logging.getLogger(__name__)

DATA_DIR = Path(__file__).parent.parent / "data"

# ---------------------------------------------------------------------------
# Tool functions — plain Python functions; ADK auto-wraps them as FunctionTool
# ---------------------------------------------------------------------------


def get_weather_data() -> dict:
    """Fetch the latest NOAA weather/storm data for Tampa Bay.

    Returns:
        dict: Storm information including name, category, wind speed,
              trajectory, warnings, and tide data.
    """
    with open(DATA_DIR / "sample_weather.json") as f:
        return json.load(f)


def get_zone_data() -> list[dict]:
    """Fetch Tampa Bay evacuation zone data with baseline risk scores.

    Returns:
        list[dict]: List of neighborhood objects each containing
            neighborhood name, evacuation zone letter, lat/lng,
            baseline flood_risk, storm_surge_ft, time_to_impact_hours,
            and recommendation.
    """
    with open(DATA_DIR / "tampa_zones.json") as f:
        return json.load(f)


def save_risk_assessments(assessments: list[dict]) -> dict:
    """Save the computed risk assessments to the database.

    Each assessment dict must contain:
        neighborhood (str), zone (str), lat (float), lng (float),
        flood_risk (float 0-1), storm_surge_ft (float),
        time_to_impact_hours (float), recommendation (str),
        evacuate_by (str ISO timestamp or empty string).

    Args:
        assessments: List of risk assessment dicts, one per neighborhood.

    Returns:
        dict: Status message with count of saved assessments.
    """
    conn = get_connection()
    # Clear previous assessments so we always have fresh data
    conn.execute("DELETE FROM risk_assessments")

    saved = 0
    for a in assessments:
        try:
            ev = a.get("evacuate_by") or None
            if ev == "":
                ev = None
            conn.execute(
                """INSERT INTO risk_assessments
                   (neighborhood, zone, lat, lng, flood_risk,
                    storm_surge_ft, time_to_impact_hours,
                    recommendation, evacuate_by)
                   VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)""",
                (
                    a.get("neighborhood", ""),
                    a.get("zone", ""),
                    float(a.get("lat", 0)),
                    float(a.get("lng", 0)),
                    float(a.get("flood_risk", 0)),
                    float(a.get("storm_surge_ft", 0)),
                    float(a.get("time_to_impact_hours", 0)),
                    a.get("recommendation", ""),
                    ev,
                ),
            )
            saved += 1
        except Exception as exc:
            logger.error("Failed to save assessment for %s: %s", a.get("neighborhood"), exc)

    conn.commit()
    conn.close()
    return {"status": "success", "saved_count": saved}


# ---------------------------------------------------------------------------
# Agent definition
# ---------------------------------------------------------------------------

MONITOR_INSTRUCTION = """\
You are the Aegis Monitor Agent — a disaster intelligence analyst specializing
in hurricane risk assessment for Tampa Bay, Florida.

Your job:
1. Call get_weather_data() to retrieve the current NOAA storm data.
2. Call get_zone_data() to retrieve Tampa Bay neighborhood evacuation zones
   with their baseline risk profiles.
3. Analyze the storm trajectory, wind speed, pressure, storm surge warnings,
   and tide data in relation to each neighborhood's geographic position,
   evacuation zone, and elevation vulnerability.
4. For each neighborhood, compute an updated risk assessment:
   - flood_risk: float 0.0 - 1.0 (incorporate storm category, surge
     forecast, proximity to coast, and zone designation)
   - storm_surge_ft: estimated storm surge in feet for that location
   - time_to_impact_hours: hours until dangerous conditions arrive
   - recommendation: one of "evacuate", "shelter_in_place", or "monitor"
   - evacuate_by: ISO 8601 timestamp if recommendation is "evacuate",
     calculated as current time + time_to_impact_hours minus a 6-hour
     safety buffer; empty string otherwise
5. Call save_risk_assessments() with the full list of assessment dicts.
   Each dict must include: neighborhood, zone, lat, lng, flood_risk,
   storm_surge_ft, time_to_impact_hours, recommendation, evacuate_by.
6. After saving, provide a brief text summary of the overall threat level
   and key findings.

CRITICAL RULES:
- You MUST produce exactly one assessment for EVERY neighborhood returned by get_zone_data(). Do NOT skip any.
- Use the neighborhood name, zone, lat, and lng exactly as returned by get_zone_data().
- Be precise with numbers. Zone A neighborhoods near the coast are most
  vulnerable to storm surge. Factor in the storm's current category, movement
  speed, and predicted tide peak when computing risk scores.
"""


def _get_model():
    """Pick the best available model — Groq if key exists, else Gemini."""
    if GROQ_API_KEY:
        return LiteLlm(model="groq/llama-3.3-70b-versatile")
    return "gemini-2.0-flash"


def _build_monitor_agent() -> Agent:
    """Create a fresh Monitor Agent instance."""
    return Agent(
        name="monitor_agent",
        model=_get_model(),
        description=(
            "Analyzes NOAA weather data and Tampa Bay evacuation zones to "
            "produce per-neighborhood flood risk scores and evacuation "
            "recommendations."
        ),
        instruction=MONITOR_INSTRUCTION,
        tools=[get_weather_data, get_zone_data, save_risk_assessments],
    )


# ---------------------------------------------------------------------------
# Runner helper — called from the API route
# ---------------------------------------------------------------------------

APP_NAME = "aegis"


async def run_monitor_agent() -> dict[str, Any]:
    """Execute the Monitor Agent end-to-end and return results.

    Returns a dict with:
        - status: "success" or "error"
        - summary: text summary from the agent
        - assessments: list of dicts from the DB
    """
    # Ensure API keys are available
    if GROQ_API_KEY:
        os.environ.setdefault("GROQ_API_KEY", GROQ_API_KEY)
    if GEMINI_API_KEY:
        os.environ.setdefault("GOOGLE_API_KEY", GEMINI_API_KEY)

    agent = _build_monitor_agent()
    session_service = InMemorySessionService()
    runner = Runner(
        agent=agent,
        app_name=APP_NAME,
        session_service=session_service,
    )

    user_id = "aegis_system"
    session_id = f"monitor_{uuid.uuid4().hex[:8]}"

    # Create a session
    session = await session_service.create_session(
        app_name=APP_NAME,
        user_id=user_id,
        session_id=session_id,
    )

    # Kick off the agent with a prompt
    user_message = types.Content(
        role="user",
        parts=[types.Part(text=(
            "Analyze the current storm data and Tampa Bay evacuation zones. "
            "Compute updated risk assessments for every neighborhood and save "
            "them to the database. Provide a brief summary of findings."
        ))],
    )

    agent_response_text = ""

    async for event in runner.run_async(
        user_id=user_id,
        session_id=session.id,
        new_message=user_message,
    ):
        if event.is_final_response() and event.content and event.content.parts:
            agent_response_text = event.content.parts[0].text

    # Fetch the saved assessments from DB
    conn = get_connection()
    rows = conn.execute(
        "SELECT * FROM risk_assessments ORDER BY flood_risk DESC"
    ).fetchall()
    conn.close()

    assessments = [dict(r) for r in rows]

    return {
        "status": "success",
        "summary": agent_response_text,
        "assessments": assessments,
    }
