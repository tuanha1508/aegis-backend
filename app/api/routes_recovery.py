import json
import logging
import os
import uuid

from fastapi import APIRouter, HTTPException

from google.adk.agents import Agent
from google.adk.models.lite_llm import LiteLlm
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.genai import types

from app.config import GEMINI_API_KEY, GROQ_API_KEY
from app.db.database import get_connection

router = APIRouter(tags=["recovery"])
logger = logging.getLogger(__name__)


@router.get("/recovery/briefs")
async def get_briefs():
    conn = get_connection()
    try:
        rows = conn.execute(
            "SELECT * FROM recovery_briefs ORDER BY generated_at DESC"
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


@router.get("/recovery/briefs/{neighborhood}")
async def get_brief(neighborhood: str):
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT * FROM recovery_briefs WHERE neighborhood = %s", (neighborhood,)
        ).fetchone()
        if not row:
            raise HTTPException(
                status_code=404, detail="Brief not found for neighborhood"
            )
        return dict(row)
    finally:
        conn.close()


# ─── Recovery Brief Generation ────────────────────────────────

def _get_neighborhood_context() -> dict:
    """Gather all current data needed to generate recovery briefs."""
    conn = get_connection()
    try:
        neighborhoods = [r["neighborhood"] for r in conn.execute(
            "SELECT DISTINCT neighborhood FROM risk_assessments"
        ).fetchall()]
        incidents = [dict(r) for r in conn.execute(
            "SELECT * FROM incidents ORDER BY severity_score DESC NULLS LAST"
        ).fetchall()]
        resources = [dict(r) for r in conn.execute(
            "SELECT * FROM resources WHERE status IN ('open', 'limited')"
        ).fetchall()]
        alerts = [dict(r) for r in conn.execute(
            "SELECT * FROM alerts ORDER BY created_at DESC LIMIT 20"
        ).fetchall()]
    finally:
        conn.close()

    return {
        "neighborhoods": neighborhoods,
        "incidents": incidents,
        "resources": resources,
        "alerts": alerts,
    }


def _save_brief(brief: dict) -> int:
    """Save a recovery brief to the database."""
    conn = get_connection()
    try:
        row = conn.execute(
            """INSERT INTO recovery_briefs
               (neighborhood, power_status, water_status, roads_status,
                shelters_nearby, medical_nearby, key_updates)
               VALUES (%s, %s, %s, %s, %s, %s, %s) RETURNING id""",
            (
                brief.get("neighborhood", ""),
                brief.get("power_status", ""),
                brief.get("water_status", ""),
                brief.get("roads_status", ""),
                brief.get("shelters_nearby", ""),
                brief.get("medical_nearby", ""),
                brief.get("key_updates", ""),
            ),
        ).fetchone()
        conn.commit()
        return row["id"] if row else 0
    finally:
        conn.close()


RECOVERY_INSTRUCTION = """\
You are the Aegis Recovery Agent for Tampa Bay post-storm recovery.

You will receive data about neighborhoods, incidents, resources, and alerts.
Generate a recovery brief for EACH neighborhood.

For each neighborhood, call save_recovery_brief() with:
- neighborhood: the neighborhood name
- power_status: estimate based on incidents (e.g. "Restoration in progress — estimated 24-48 hours")
- water_status: based on flooding incidents (e.g. "Boil water advisory in effect")
- roads_status: based on road_blocked incidents (e.g. "Major routes clearing, avoid side streets")
- shelters_nearby: JSON array of nearby shelter names
- medical_nearby: JSON array of nearby medical facility names
- key_updates: JSON array of 2-3 key recovery updates for residents

Be specific and actionable. Use real shelter and facility names from the data.
"""


def _get_model():
    if GROQ_API_KEY:
        return LiteLlm(model="groq/llama-3.3-70b-versatile")
    return "gemini-2.5-flash"  # ADK accepts bare string for Gemini models


@router.post("/recovery/generate")
async def generate_recovery_briefs():
    """Generate recovery briefs for all neighborhoods using AI."""
    if GROQ_API_KEY:
        os.environ.setdefault("GROQ_API_KEY", GROQ_API_KEY)
    if GEMINI_API_KEY:
        os.environ.setdefault("GOOGLE_API_KEY", GEMINI_API_KEY)

    context = _get_neighborhood_context()

    def save_recovery_brief(
        neighborhood: str,
        power_status: str,
        water_status: str,
        roads_status: str,
        shelters_nearby: str,
        medical_nearby: str,
        key_updates: str,
    ) -> dict:
        """Save a recovery brief for a neighborhood.

        Args:
            neighborhood: Name of the neighborhood.
            power_status: Current power restoration status.
            water_status: Water safety status.
            roads_status: Road accessibility status.
            shelters_nearby: JSON array string of nearby shelter names.
            medical_nearby: JSON array string of nearby medical facility names.
            key_updates: JSON array string of key recovery updates.

        Returns:
            dict with status and brief_id.
        """
        brief_id = _save_brief({
            "neighborhood": neighborhood,
            "power_status": power_status,
            "water_status": water_status,
            "roads_status": roads_status,
            "shelters_nearby": shelters_nearby,
            "medical_nearby": medical_nearby,
            "key_updates": key_updates,
        })
        return {"status": "saved", "brief_id": brief_id}

    agent = Agent(
        name="recovery_agent",
        model=_get_model(),
        description="Generates post-storm recovery briefs for Tampa Bay neighborhoods.",
        instruction=RECOVERY_INSTRUCTION,
        tools=[save_recovery_brief],
    )

    session_service = InMemorySessionService()
    runner = Runner(agent=agent, app_name="aegis", session_service=session_service)
    session = await session_service.create_session(
        app_name="aegis", user_id="aegis_system",
        session_id=f"recovery_{uuid.uuid4().hex[:8]}",
    )

    prompt = (
        f"Generate recovery briefs for these neighborhoods: {context['neighborhoods']}\n\n"
        f"Current incidents: {json.dumps(context['incidents'][:10], default=str)}\n\n"
        f"Available resources: {json.dumps(context['resources'][:15], default=str)}\n\n"
        f"Recent alerts: {json.dumps(context['alerts'][:5], default=str)}"
    )

    user_message = types.Content(role="user", parts=[types.Part(text=prompt)])

    final_text = ""
    try:
        async for event in runner.run_async(
            user_id="aegis_system", session_id=session.id, new_message=user_message,
        ):
            if event.is_final_response() and event.content and event.content.parts:
                final_text = event.content.parts[0].text
    except Exception as e:
        logger.error("Recovery Agent error: %s", e)
        return {"status": "error", "error": str(e)}

    conn = get_connection()
    try:
        rows = conn.execute(
            "SELECT * FROM recovery_briefs ORDER BY generated_at DESC"
        ).fetchall()
    finally:
        conn.close()

    return {
        "status": "success",
        "summary": final_text,
        "briefs": [dict(r) for r in rows],
        "briefs_count": len(rows),
    }
