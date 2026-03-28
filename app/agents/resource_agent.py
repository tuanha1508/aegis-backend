"""
Resource Agent — Tracks and manages emergency resources for Tampa Bay.

Uses Google ADK + Gemini to monitor shelter capacity, find nearest resources,
factor in road accessibility, and recommend resource deployments based on
active incidents.
"""

from __future__ import annotations

import json
import logging
import math
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


def get_all_resources() -> dict:
    """Fetch all resources (shelters, medical stations, supply depots) from the database.

    Returns:
        dict: List of resources with type, name, location, capacity,
              current occupancy, amenities, and status.
    """
    conn = get_connection()
    try:
        rows = conn.execute(
            "SELECT * FROM resources ORDER BY type, name"
        ).fetchall()
    finally:
        conn.close()

    if not rows:
        return {"status": "no_resources", "resources": []}

    return {"status": "ok", "count": len(rows), "resources": [dict(r) for r in rows]}


def update_resource_status(
    resource_id: int,
    status: str,
    current_occupancy: int,
    notes: str,
) -> dict:
    """Update the status and occupancy of a resource.

    Args:
        resource_id: Database ID of the resource.
        status: New status — one of 'open', 'full', 'closed', 'limited'.
        current_occupancy: Current number of people at this resource.
        notes: Free-text notes about the resource status.

    Returns:
        dict: Status and updated resource data.
    """
    conn = get_connection()
    try:
        conn.execute(
            """UPDATE resources SET
               status = %s, current_occupancy = %s, notes = %s,
               last_updated = NOW()
               WHERE id = %s""",
            (status, current_occupancy, notes, resource_id),
        )
        conn.commit()

        row = conn.execute("SELECT * FROM resources WHERE id = %s", (resource_id,)).fetchone()
    finally:
        conn.close()

    if row:
        return {"status": "updated", "resource": dict(row)}
    return {"status": "error", "message": f"Resource {resource_id} not found"}


def get_incidents_needing_resources() -> dict:
    """Fetch unresolved incidents that may need resource deployment.

    Returns incidents ranked by severity so the agent can recommend
    which resources to deploy where.
    """
    conn = get_connection()
    try:
        rows = conn.execute(
            """SELECT * FROM incidents
               WHERE resolved = FALSE
               ORDER BY severity_score DESC"""
        ).fetchall()
    finally:
        conn.close()

    if not rows:
        return {"status": "no_incidents", "incidents": []}

    return {"status": "ok", "count": len(rows), "incidents": [dict(r) for r in rows]}


def find_nearest_resource(lat: float, lng: float, resource_type: str) -> dict:
    """Find the nearest open resource of a given type to a location.

    Args:
        lat: Latitude of the location needing resources.
        lng: Longitude of the location needing resources.
        resource_type: Type of resource needed ('shelter', 'medical', 'supply').

    Returns:
        dict: The nearest resource with its distance in miles.
    """
    conn = get_connection()
    try:
        rows = conn.execute(
            "SELECT * FROM resources WHERE type = %s AND status IN ('open', 'limited')",
            (resource_type,),
        ).fetchall()
    finally:
        conn.close()

    if not rows:
        return {"status": "none_available", "resource_type": resource_type}

    # Calculate distances (Haversine approximation)
    best = None
    best_dist = float("inf")
    for row in rows:
        r = dict(row)
        dlat = math.radians(r["lat"] - lat)
        dlng = math.radians(r["lng"] - lng)
        a = (math.sin(dlat / 2) ** 2 +
             math.cos(math.radians(lat)) * math.cos(math.radians(r["lat"])) *
             math.sin(dlng / 2) ** 2)
        dist_miles = 3959 * 2 * math.asin(math.sqrt(a))
        if dist_miles < best_dist:
            best_dist = dist_miles
            best = r

    best["distance_miles"] = round(best_dist, 2)
    return {"status": "found", "resource": best}


# ---------------------------------------------------------------------------
# Agent Definition
# ---------------------------------------------------------------------------

RESOURCE_INSTRUCTION = """\
You are the Aegis Resource Agent for Tampa Bay disaster response.

Your job is to monitor and manage emergency resources — shelters, medical
stations, and supply depots — ensuring they are deployed effectively based
on current incidents and demand.

## Your Workflow

1. Call `get_all_resources()` to see current resource status and capacity.
2. Call `get_incidents_needing_resources()` to see active incidents.
3. For each high-severity incident, call `find_nearest_resource()` to locate
   the closest available resource.
4. Analyze capacity vs. demand and update resource statuses as needed using
   `update_resource_status()`.
5. Provide a summary of resource status and recommendations.

## Resource Management Rules

### Capacity Thresholds
- Open: occupancy < 80% of capacity
- Limited: occupancy 80-95% of capacity
- Full: occupancy >= 95% of capacity

### Priority Deployment
- Critical incidents (score 75+) → nearest shelter + medical
- High incidents (score 50-74) → nearest shelter
- Supply needs → direct supply deployment

### Recommendations
- If a shelter is > 90% full, recommend redirecting to the next nearest.
- If multiple incidents cluster in one area, recommend staging a supply depot.
- Track shelter amenities to match needs (medical_station for injuries,
  pet_friendly for evacuees with pets).

## CRITICAL RULES
- Always check current capacity before recommending a shelter.
- Update status to 'full' or 'limited' based on occupancy thresholds.
- Factor in distance — don't recommend a far shelter when a closer one is open.
- Provide specific, actionable recommendations.
"""


def _get_model():
    """Pick the best available model — Groq if key exists, else Gemini."""
    if GROQ_API_KEY:
        return LiteLlm(model="groq/llama-3.3-70b-versatile")
    return "gemini-2.0-flash"


def _build_resource_agent() -> Agent:
    """Create a fresh Resource Agent instance."""
    return Agent(
        name="resource_agent",
        model=_get_model(),
        description=(
            "Tracks shelter capacity, finds nearest resources, monitors demand "
            "from active incidents, and recommends resource deployments."
        ),
        instruction=RESOURCE_INSTRUCTION,
        tools=[get_all_resources, update_resource_status, get_incidents_needing_resources, find_nearest_resource],
    )


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------

APP_NAME = "aegis"


async def run_resource_agent() -> dict[str, Any]:
    """Execute the Resource Agent to analyze and manage resources.

    Returns a dict with:
        - status: "success" or "error"
        - summary: text summary from the agent
        - resources: current state of all resources
    """
    if GROQ_API_KEY:
        os.environ.setdefault("GROQ_API_KEY", GROQ_API_KEY)
    if GEMINI_API_KEY:
        os.environ.setdefault("GOOGLE_API_KEY", GEMINI_API_KEY)

    agent = _build_resource_agent()
    session_service = InMemorySessionService()
    runner = Runner(
        agent=agent,
        app_name=APP_NAME,
        session_service=session_service,
    )

    user_id = "aegis_system"
    session_id = f"resource_{uuid.uuid4().hex[:8]}"

    session = await session_service.create_session(
        app_name=APP_NAME,
        user_id=user_id,
        session_id=session_id,
    )

    user_message = types.Content(
        role="user",
        parts=[types.Part(text=(
            "Review all resources and active incidents. Update resource statuses "
            "based on current demand, find nearest resources for each incident, "
            "and provide recommendations for resource deployment."
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
        logger.error("Resource Agent error: %s", e)
        return {"status": "error", "error": str(e), "resources": []}

    # Fetch current resource state
    conn = get_connection()
    try:
        rows = conn.execute("SELECT * FROM resources ORDER BY type, name").fetchall()
    finally:
        conn.close()

    resources = [dict(r) for r in rows]

    return {
        "status": "success",
        "summary": final_text,
        "resources": resources,
    }
