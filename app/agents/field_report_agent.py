"""
Field Report Agent — Parses raw disaster reports into structured data.

Uses Google ADK + Gemini to extract location, geocode using Tampa reference
data, classify incident type, detect language, and count people mentioned.
Results are persisted to the reports table in PostgreSQL (Supabase).
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
# ADK Tool Functions
# ---------------------------------------------------------------------------


def get_unprocessed_reports() -> dict:
    """Fetch all unprocessed field reports from the database.

    Returns:
        dict: List of reports where processed=0, including id, raw_text,
              source, sender_phone, and created_at.
    """
    conn = get_connection()
    try:
        rows = conn.execute(
            "SELECT * FROM reports WHERE processed = false ORDER BY created_at ASC"
        ).fetchall()
    finally:
        conn.close()

    if not rows:
        return {"status": "no_data", "reports": []}

    return {"status": "ok", "count": len(rows), "reports": [dict(r) for r in rows]}


def get_tampa_locations() -> dict:
    """Get Tampa Bay reference locations for geocoding field reports.

    Returns a dictionary containing:
    - neighborhoods: List of Tampa neighborhoods with lat/lng coordinates
    - shelters: List of shelter locations with names and coordinates
    - landmarks: Common Tampa Bay landmarks and intersections

    Use this data to match location mentions in reports to coordinates.
    """
    with open(DATA_DIR / "tampa_zones.json") as f:
        zones = json.load(f)

    with open(DATA_DIR / "tampa_shelters.json") as f:
        shelters = json.load(f)

    # Add well-known Tampa landmarks for geocoding
    landmarks = [
        {"name": "Bay to Bay Blvd", "lat": 27.912, "lng": -82.493, "area": "South Tampa"},
        {"name": "Dale Mabry and Gandy", "lat": 27.891, "lng": -82.507, "area": "South Tampa"},
        {"name": "Henderson Blvd", "lat": 27.929, "lng": -82.515, "area": "South Tampa"},
        {"name": "Bayshore Blvd", "lat": 27.920, "lng": -82.475, "area": "Hyde Park"},
        {"name": "Kennedy Blvd", "lat": 27.947, "lng": -82.461, "area": "Downtown Tampa"},
        {"name": "Hillsborough Ave", "lat": 27.974, "lng": -82.457, "area": "Seminole Heights"},
        {"name": "Gandy Bridge", "lat": 27.880, "lng": -82.530, "area": "South Tampa"},
        {"name": "Howard Frankland Bridge", "lat": 27.924, "lng": -82.555, "area": "Tampa Bay"},
        {"name": "Courtney Campbell Causeway", "lat": 27.967, "lng": -82.577, "area": "Tampa Bay"},
        {"name": "MacDill Air Force Base", "lat": 27.850, "lng": -82.511, "area": "South Tampa"},
        {"name": "Tampa General Hospital", "lat": 27.937, "lng": -82.452, "area": "Davis Islands"},
        {"name": "Tampa International Airport", "lat": 27.975, "lng": -82.533, "area": "Westshore"},
    ]

    return {
        "neighborhoods": [{"name": z["neighborhood"], "lat": z["lat"], "lng": z["lng"], "zone": z["zone"]} for z in zones],
        "shelters": [{"name": s["name"], "lat": s["lat"], "lng": s["lng"]} for s in shelters],
        "landmarks": landmarks,
    }


def _nearest_neighborhood(lat: float, lng: float) -> str:
    """Find the nearest Tampa neighborhood name for given coordinates."""
    import math
    with open(DATA_DIR / "tampa_zones.json") as f:
        zones = json.load(f)
    best_name = "Tampa Bay Area"
    best_dist = float("inf")
    for z in zones:
        dlat = lat - z["lat"]
        dlng = lng - z["lng"]
        dist = math.sqrt(dlat * dlat + dlng * dlng)
        if dist < best_dist:
            best_dist = dist
            best_name = z["neighborhood"]
    return best_name


def parse_report(
    report_id: int,
    location_text: str,
    lat: float,
    lng: float,
    incident_type: str,
    people_mentioned: int,
    has_children: int,
    language: str,
) -> dict:
    """Save parsed fields for a report, marking it as processed.

    Args:
        report_id: The database ID of the report to update.
        location_text: Human-readable location extracted from the report text.
            Must be a specific street, landmark, or neighborhood name — never
            "Unknown" or empty. If unsure, use the nearest Tampa neighborhood.
        lat: Latitude coordinate for the location (use Tampa reference data).
        lng: Longitude coordinate for the location (use Tampa reference data).
        incident_type: One of: 'flooding', 'trapped_person', 'road_blocked',
                       'power_outage', 'supply_needed', 'resource_status',
                       'structural_damage', 'medical_emergency', 'fire', 'looting', 'other'.
        people_mentioned: Number of people mentioned in the report (0 if none).
        has_children: 1 if children are mentioned, 0 otherwise.
        language: Detected language code ('en', 'es', 'ht', etc.).

    Returns:
        dict: Status and the updated report data.
    """
    # Enrich: if location_text is vague, use nearest neighborhood
    if not location_text or location_text.lower() in ("unknown", "n/a", "none", ""):
        location_text = _nearest_neighborhood(lat, lng)

    # Enrich: append nearest neighborhood for context
    neighborhood = _nearest_neighborhood(lat, lng)

    conn = get_connection()
    try:
        conn.execute(
            """UPDATE reports SET
               location_text = %s, lat = %s, lng = %s, incident_type = %s,
               people_mentioned = %s, has_children = %s, language = %s, processed = TRUE
               WHERE id = %s""",
            (
                location_text,
                lat,
                lng,
                incident_type,
                people_mentioned,
                bool(has_children),
                language,
                report_id,
            ),
        )
        conn.commit()

        row = conn.execute("SELECT * FROM reports WHERE id = %s", (report_id,)).fetchone()
    finally:
        conn.close()

    if row:
        result = dict(row)
        result["neighborhood"] = neighborhood
        return {"status": "success", "report": result}
    return {"status": "error", "message": f"Report {report_id} not found"}


# ---------------------------------------------------------------------------
# Agent Definition
# ---------------------------------------------------------------------------

FIELD_REPORT_INSTRUCTION = """\
You are the Aegis Field Report Agent for Tampa Bay disaster response.

Your job is to parse raw disaster reports into structured data that can be
used for incident tracking and emergency response.

## Your Workflow

1. Call `get_unprocessed_reports()` to see all unprocessed field reports.
2. Call `get_tampa_locations()` to load Tampa Bay reference locations for geocoding.
3. For EACH unprocessed report, analyze the raw text and extract:
   - **location_text**: The specific location mentioned (street name, neighborhood,
     or landmark). NEVER use "Unknown" — if no specific location is mentioned,
     use the best-matching Tampa neighborhood from the reference data.
   - **lat/lng**: Geocode using the Tampa reference data. Match to the closest
     known location (neighborhood, shelter, or landmark). If the report mentions
     a general area like "South Tampa", use that neighborhood's coordinates.
   - **incident_type**: Classify as one of: 'flooding', 'trapped_person',
     'road_blocked', 'power_outage', 'supply_needed', 'resource_status',
     'structural_damage', 'medical_emergency', 'fire', 'looting', 'other'
   - **people_mentioned**: Count of people mentioned (0 if none specified)
   - **has_children**: 1 if children are mentioned or implied, 0 otherwise
   - **language**: Detect the language ('en' for English, 'es' for Spanish, etc.)
4. Call `parse_report()` for each report with the extracted fields.
5. After processing all reports, provide a brief summary.

## Classification Rules

- **resource_status** (IMPORTANT): Use when the message is mainly about whether a **named shelter,
  distribution point, food bank, or supply location** is full, closed, out of food/water, or
  running low — NOT when the reporter is asking for personal supplies at their location (that is
  `supply_needed`). Examples: "First Baptist shelter is full", "Feeding Tampa Bay ran out of water",
  "Convention center shelter at capacity", "Metropolitan Ministries closed".
- "flooding", "water rising", "water entering" → flooding
- "trapped", "stuck", "can't get out", "stranded" → trapped_person
- "tree down", "road blocked", "road closed" → road_blocked
- "power out", "no electricity", "lights out" → power_outage
- "need supplies", "need water", "need food", "need blankets" (reporter needs help at their
  location) → supply_needed
- "building damage", "roof collapsed", "wall down" → structural_damage
- "injured", "medical", "heart attack", "bleeding" → medical_emergency
- "fire", "burning", "smoke" → fire

## Geocoding Rules

- Match location mentions against the Tampa reference data.
- Use the closest matching neighborhood, shelter, or landmark coordinates.
- If an exact match isn't found, use the coordinates of the neighborhood
  that best fits the description.
- For street names, find the nearest landmark or neighborhood.

## CRITICAL RULES

- Process EVERY unprocessed report. Do not skip any.
- Always call parse_report() for each report — do not just analyze without saving.
- Be precise with coordinates. Use the reference data, don't make up coordinates.
"""


def _get_model():
    """Pick the best available model — Groq if key exists, else Gemini."""
    if GROQ_API_KEY:
        return LiteLlm(model="groq/llama-3.3-70b-versatile")
    return "gemini-2.5-flash"


def _build_field_report_agent() -> Agent:
    """Create a fresh Field Report Agent instance."""
    return Agent(
        name="field_report_agent",
        model=_get_model(),
        description=(
            "Parses raw disaster field reports into structured data by extracting "
            "location, geocoding, classifying incident type, detecting language, "
            "and counting people mentioned."
        ),
        instruction=FIELD_REPORT_INSTRUCTION,
        tools=[get_unprocessed_reports, get_tampa_locations, parse_report],
    )


# ---------------------------------------------------------------------------
# Runner helpers
# ---------------------------------------------------------------------------

APP_NAME = "aegis"


async def run_field_report_agent() -> dict[str, Any]:
    """Execute the Field Report Agent to batch-process unprocessed reports.

    Returns a dict with:
        - status: "success" or "error"
        - summary: text summary from the agent
        - processed_count: number of reports processed
    """
    if GROQ_API_KEY:
        os.environ.setdefault("GROQ_API_KEY", GROQ_API_KEY)
    if GEMINI_API_KEY:
        os.environ.setdefault("GOOGLE_API_KEY", GEMINI_API_KEY)

    agent = _build_field_report_agent()
    session_service = InMemorySessionService()
    runner = Runner(
        agent=agent,
        app_name=APP_NAME,
        session_service=session_service,
    )

    user_id = "aegis_system"
    session_id = f"field_report_{uuid.uuid4().hex[:8]}"

    session = await session_service.create_session(
        app_name=APP_NAME,
        user_id=user_id,
        session_id=session_id,
    )

    user_message = types.Content(
        role="user",
        parts=[types.Part(text=(
            "Process all unprocessed field reports. Extract location, incident type, "
            "people count, and language for each. Use Tampa Bay reference data for "
            "geocoding. Save the parsed data for every report."
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
        logger.error("Field Report Agent error: %s", e)
        return {"status": "error", "error": str(e), "processed_count": 0}

    # Count how many were processed
    conn = get_connection()
    try:
        count = conn.execute(
            "SELECT COUNT(*) AS cnt FROM reports WHERE processed = TRUE"
        ).fetchone()["cnt"]
    finally:
        conn.close()

    return {
        "status": "success",
        "summary": final_text,
        "processed_count": count,
    }


async def run_field_report_agent_single(
    report_id: int,
    raw_text: str,
    user_lat: float | None = None,
    user_lng: float | None = None,
) -> dict[str, Any]:
    """Process a single report interactively and return the AI's response.

    Used by the SMS chat simulator — processes one report and returns
    a conversational AI reply along with the structured data.

    Args:
        report_id: DB id of the stored report.
        raw_text: The raw message text.
        user_lat: GPS latitude from the user's device (if available).
        user_lng: GPS longitude from the user's device (if available).
    """
    if GROQ_API_KEY:
        os.environ.setdefault("GROQ_API_KEY", GROQ_API_KEY)
    if GEMINI_API_KEY:
        os.environ.setdefault("GOOGLE_API_KEY", GEMINI_API_KEY)

    # Build GPS context for the agent
    gps_context = ""
    if user_lat is not None and user_lng is not None:
        neighborhood = _nearest_neighborhood(user_lat, user_lng)
        gps_context = (
            f"\n\nThe user's GPS location is: lat={user_lat}, lng={user_lng} "
            f"(near {neighborhood}). Use these exact coordinates for lat/lng "
            f"and use '{neighborhood}' as the location_text if the message "
            f"doesn't mention a specific street or landmark."
        )

    prompt = (
        f"A field report was just submitted (report ID: {report_id}):\n\n"
        f"\"{raw_text}\"{gps_context}\n\n"
        "1. Call get_tampa_locations() to load reference data.\n"
        "2. Analyze this report and extract all fields.\n"
        "3. For location_text, ALWAYS use a specific street name, landmark, "
        "or neighborhood — NEVER use 'Unknown'. If the report doesn't mention "
        "a location, use the GPS neighborhood above.\n"
        "4. Call parse_report() to save the structured data.\n"
        "5. After saving, respond with a brief, helpful acknowledgment message "
        "that a disaster response bot would send back to the person who "
        "submitted this report. Keep it under 2 sentences. Include what you "
        "understood from their report and any immediate safety advice."
    )

    # Try Groq first (fast ~3s), fall back to Gemini (~10s) on failure
    from app.agents.safe_runner import run_agent_with_fallback

    def build_with_model(model):
        return Agent(
            name="field_report_agent",
            model=model,
            description=_build_field_report_agent().description,
            instruction=FIELD_REPORT_INSTRUCTION,
            tools=[get_unprocessed_reports, get_tampa_locations, parse_report],
        )

    try:
        final_text, used_fallback = await run_agent_with_fallback(
            build_with_model, prompt, "sms_chat",
        )
    except Exception as e:
        logger.error("Field Report Agent (single) error: %s", e)
        return {"status": "error", "error": str(e)}

    # Fetch the updated report and enrich with neighborhood
    conn = get_connection()
    try:
        row = conn.execute("SELECT * FROM reports WHERE id = %s", (report_id,)).fetchone()
    finally:
        conn.close()

    report = None
    if row:
        report = dict(row)
        if report.get("lat") and report.get("lng"):
            report["neighborhood"] = _nearest_neighborhood(report["lat"], report["lng"])

    return {
        "status": "success",
        "reply": final_text,
        "report": report,
    }
