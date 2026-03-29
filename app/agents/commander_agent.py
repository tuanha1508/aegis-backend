"""
Situation Commander — The "brain" that coordinates all specialist agents.

A natural language interface where operators (or judges) can ask ANY question
about the disaster situation. The Commander delegates to the right specialist
agents, synthesizes their responses, and returns a unified answer.

This demonstrates the A2A "Handshake" — one agent reaching out to specialists
to fill gaps in its own knowledge.
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
# Tool Functions — each one queries a specialist domain
# ---------------------------------------------------------------------------


def query_situation_overview() -> dict:
    """Get a complete overview of the current disaster situation.

    Returns the current phase, risk levels, incident counts, alert counts,
    resource status, and missing person counts. Use this to answer broad
    questions like "What's happening?" or "Give me a status update."
    """
    conn = get_connection()
    try:
        phase = conn.execute("SELECT current_phase FROM phase WHERE id = 1").fetchone()
        current_phase = phase["current_phase"] if phase else "unknown"

        risk = conn.execute(
            "SELECT neighborhood, flood_risk, storm_surge_ft, recommendation "
            "FROM risk_assessments ORDER BY flood_risk DESC NULLS LAST LIMIT 5"
        ).fetchall()

        incidents = conn.execute(
            "SELECT incident_type, severity_score, severity_label, location_text "
            "FROM incidents WHERE resolved = FALSE "
            "ORDER BY severity_score DESC NULLS LAST LIMIT 5"
        ).fetchall()

        alerts = conn.execute(
            "SELECT priority, title, neighborhood FROM alerts "
            "ORDER BY created_at DESC LIMIT 5"
        ).fetchall()

        resources = conn.execute(
            "SELECT type, COUNT(*) AS cnt FROM resources "
            "WHERE status IN ('open', 'limited') GROUP BY type"
        ).fetchall()

        missing = conn.execute(
            "SELECT COUNT(*) AS cnt FROM missing_persons WHERE status = 'missing'"
        ).fetchone()["cnt"]

        unresolved = conn.execute(
            "SELECT COUNT(*) AS cnt FROM incidents WHERE resolved = FALSE"
        ).fetchone()["cnt"]
    finally:
        conn.close()

    return {
        "current_phase": current_phase,
        "top_risks": [dict(r) for r in risk],
        "critical_incidents": [dict(i) for i in incidents],
        "recent_alerts": [dict(a) for a in alerts],
        "available_resources": [dict(r) for r in resources],
        "missing_persons_count": missing,
        "unresolved_incidents": unresolved,
    }


def query_neighborhood_status(neighborhood: str) -> dict:
    """Get detailed status for a specific Tampa Bay neighborhood.

    Args:
        neighborhood: Name like "Davis Islands", "South Tampa", "Ruskin", etc.

    Returns risk level, incidents, nearby resources, and recovery status.
    """
    conn = get_connection()
    try:
        risk = conn.execute(
            "SELECT * FROM risk_assessments WHERE neighborhood ILIKE %s",
            (f"%{neighborhood}%",),
        ).fetchone()

        incidents = conn.execute(
            "SELECT * FROM incidents WHERE location_text ILIKE %s AND resolved = FALSE "
            "ORDER BY severity_score DESC NULLS LAST",
            (f"%{neighborhood}%",),
        ).fetchall()

        recovery = conn.execute(
            "SELECT * FROM recovery_briefs WHERE neighborhood ILIKE %s "
            "ORDER BY generated_at DESC LIMIT 1",
            (f"%{neighborhood}%",),
        ).fetchone()
    finally:
        conn.close()

    return {
        "neighborhood": neighborhood,
        "risk": dict(risk) if risk else None,
        "active_incidents": [dict(i) for i in incidents],
        "recovery_brief": dict(recovery) if recovery else None,
    }


def query_missing_person(name: str) -> dict:
    """Search for a missing person by name and check for matches.

    Args:
        name: Full or partial name to search for.

    Returns missing person details and any potential matches found.
    """
    conn = get_connection()
    try:
        missing = conn.execute(
            "SELECT * FROM missing_persons WHERE name ILIKE %s",
            (f"%{name}%",),
        ).fetchall()

        results = []
        for m in missing:
            md = dict(m)
            matches = conn.execute(
                "SELECT m.*, f.name AS found_name, f.found_at, f.description AS found_description "
                "FROM matches m JOIN found_persons f ON m.found_id = f.id "
                "WHERE m.missing_id = %s ORDER BY m.confidence DESC",
                (md["id"],),
            ).fetchall()
            md["potential_matches"] = [dict(match) for match in matches]
            results.append(md)
    finally:
        conn.close()

    return {"search_name": name, "results": results}


def query_resources(resource_type: str) -> dict:
    """Get available resources filtered by type.

    Args:
        resource_type: One of 'shelter', 'medical', 'fire_station', or 'all'.

    Returns list of resources with capacity and status.
    """
    conn = get_connection()
    try:
        if resource_type == "all":
            rows = conn.execute(
                "SELECT * FROM resources ORDER BY type, name"
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM resources WHERE type = %s ORDER BY name",
                (resource_type,),
            ).fetchall()
    finally:
        conn.close()

    return {
        "type_filter": resource_type,
        "count": len(rows),
        "resources": [dict(r) for r in rows],
    }


def query_recent_reports() -> dict:
    """Get the most recent field reports with their parsed data.

    Returns the latest 10 reports showing what incidents are being
    reported from the field.
    """
    conn = get_connection()
    try:
        rows = conn.execute(
            "SELECT * FROM reports ORDER BY created_at DESC LIMIT 10"
        ).fetchall()
    finally:
        conn.close()

    return {"count": len(rows), "reports": [dict(r) for r in rows]}


def query_weather_and_storm() -> dict:
    """Get current weather conditions and storm data.

    Returns real-time NWS weather observation, storm scenario data,
    and tide levels for Tampa Bay.
    """
    from app.services.weather_service import get_weather_data
    storm = get_weather_data()

    # Also get live weather if available
    live = {}
    try:
        conn = get_connection()
        try:
            # Get latest orchestration scenario
            orch = conn.execute(
                "SELECT scenario_step, operational_mode FROM orchestration_state WHERE id = 1"
            ).fetchone()
            if orch:
                live["scenario"] = orch["scenario_step"]
                live["mode"] = orch["operational_mode"]
        finally:
            conn.close()
    except Exception:
        pass

    return {"storm_data": storm, "operational": live}


def trigger_agent_action(action: str) -> dict:
    """Describe an agent action that should be triggered.

    Args:
        action: One of 'analyze_risk', 'generate_alerts', 'process_reports',
                'rank_incidents', 'verify_incidents', 'match_persons',
                'generate_recovery'.

    Returns confirmation that the action has been noted for execution.
    This is informational — the actual agent will be triggered via the API.
    """
    action_map = {
        "analyze_risk": "Monitor Agent will analyze storm data and update risk scores",
        "generate_alerts": "Alert Agent will generate multilingual alerts for affected areas",
        "process_reports": "Field Report Agent will parse all unprocessed field reports",
        "rank_incidents": "Severity Agent will score and rank incidents by urgency",
        "verify_incidents": "Verification LoopAgent will review and self-correct severity scores",
        "match_persons": "Reunification Agent will match missing persons with found records",
        "generate_recovery": "Recovery Agent will generate neighborhood recovery briefs",
    }
    desc = action_map.get(action, f"Unknown action: {action}")
    return {"action": action, "description": desc, "status": "recommended"}


# ---------------------------------------------------------------------------
# Agent Definition
# ---------------------------------------------------------------------------

COMMANDER_INSTRUCTION = """\
You are the Aegis Situation Commander — the central intelligence coordinator
for Tampa Bay disaster response.

You have access to the ENTIRE Aegis system through your tools. When someone
asks a question, use the right tool to get the answer:

## Your Tools
- `query_situation_overview()` — Get the big picture: phase, risks, incidents, alerts
- `query_neighborhood_status(neighborhood)` — Deep dive into one neighborhood
- `query_missing_person(name)` — Search for a missing person and their matches
- `query_resources(resource_type)` — Check shelter/medical/fire station availability
- `query_recent_reports()` — See what's coming in from the field
- `query_weather_and_storm()` — Current storm data and weather conditions
- `trigger_agent_action(action)` — Recommend triggering a specialist agent

## Your Personality
- You are calm, authoritative, and decisive — like an emergency operations commander
- Lead with the most critical information first
- Use specific numbers: "Davis Islands at 92% flood risk, 10.5ft surge expected"
- Reference real Tampa Bay locations and shelter names
- If asked about a person, always check for matches
- If the situation is critical, recommend specific agent actions

## Example Interactions
User: "What's the situation?"
→ Call query_situation_overview(), summarize the most critical findings

User: "Is Davis Islands safe?"
→ Call query_neighborhood_status("Davis Islands"), give risk + recommendation

User: "Has Maria Garcia been found?"
→ Call query_missing_person("Maria Garcia"), report match confidence

User: "Where can people go for shelter?"
→ Call query_resources("shelter"), list open shelters with capacity

User: "What should we do next?"
→ Assess the situation, then call trigger_agent_action() for recommended actions

## CRITICAL RULES
- ALWAYS call at least one tool before responding — never guess
- Be concise but complete — commanders need fast answers
- If multiple tools are needed, call them all to build a complete picture
"""


def _get_model():
    # Commander needs reliable multi-tool calling — use Gemini directly
    return "gemini-2.5-flash"


def _build_commander_agent() -> Agent:
    return Agent(
        name="situation_commander",
        model=_get_model(),
        description=(
            "Central intelligence coordinator that queries all specialist "
            "agents and synthesizes disaster situation reports."
        ),
        instruction=COMMANDER_INSTRUCTION,
        tools=[
            query_situation_overview,
            query_neighborhood_status,
            query_missing_person,
            query_resources,
            query_recent_reports,
            query_weather_and_storm,
            trigger_agent_action,
        ],
    )


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------

APP_NAME = "aegis"


async def run_commander(question: str) -> dict[str, Any]:
    """Ask the Situation Commander a question about the disaster.

    Args:
        question: Natural language question from an operator or judge.

    Returns the commander's synthesized response.
    """
    if GROQ_API_KEY:
        os.environ.setdefault("GROQ_API_KEY", GROQ_API_KEY)
    if GEMINI_API_KEY:
        os.environ.setdefault("GOOGLE_API_KEY", GEMINI_API_KEY)

    agent = _build_commander_agent()
    session_service = InMemorySessionService()
    runner = Runner(
        agent=agent,
        app_name=APP_NAME,
        session_service=session_service,
    )

    session_id = f"commander_{uuid.uuid4().hex[:8]}"
    session = await session_service.create_session(
        app_name=APP_NAME,
        user_id="aegis_operator",
        session_id=session_id,
    )

    user_message = types.Content(
        role="user",
        parts=[types.Part(text=question)],
    )

    final_text = ""
    try:
        async for event in runner.run_async(
            user_id="aegis_operator",
            session_id=session.id,
            new_message=user_message,
        ):
            if event.is_final_response() and event.content and event.content.parts:
                final_text = event.content.parts[0].text
    except Exception as e:
        logger.error("Commander Agent error: %s", e)
        return {"status": "error", "error": str(e)}

    return {
        "status": "success",
        "question": question,
        "response": final_text,
    }
