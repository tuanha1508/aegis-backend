"""
Orchestrator — Coordinates all Aegis agents based on the current disaster phase.

Uses Google ADK SequentialAgent and ParallelAgent for phase-dependent
multi-agent orchestration:
- Pre-storm: Monitor → Alert (sequential)
- Active storm: Field Report → Severity → [Resource + Alert] (sequential + parallel)
- Post-storm: [Reunification + Resource] (parallel)
"""

from __future__ import annotations

import logging
import os
import uuid
from typing import Any

from google.adk.agents import Agent, SequentialAgent, ParallelAgent
from google.adk.models.lite_llm import LiteLlm
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.genai import types

from app.config import GEMINI_API_KEY, GROQ_API_KEY
from app.db.database import get_connection

# Import agent builders
from app.agents.monitor_agent import _build_monitor_agent
from app.agents.alert_agent import _build_alert_agent
from app.agents.field_report_agent import _build_field_report_agent
from app.agents.severity_agent import _build_severity_agent
from app.agents.resource_agent import _build_resource_agent
from app.agents.reunification_agent import _build_reunification_agent

logger = logging.getLogger(__name__)

APP_NAME = "aegis"


def _get_current_phase() -> str:
    """Read the current disaster phase from the database."""
    conn = get_connection()
    row = conn.execute("SELECT current_phase FROM phase WHERE id = 1").fetchone()
    conn.close()
    return row["current_phase"] if row else "pre_storm"


def _build_pre_storm_pipeline() -> SequentialAgent:
    """Pre-storm: Monitor → Alert (sequential)."""
    return SequentialAgent(
        name="pre_storm_pipeline",
        description="Pre-storm pipeline: analyze risk then generate alerts.",
        sub_agents=[
            _build_monitor_agent(),
            _build_alert_agent(),
        ],
    )


def _build_active_storm_pipeline() -> SequentialAgent:
    """Active storm: Field Report → Severity → [Resource + Alert] (sequential + parallel)."""
    response_parallel = ParallelAgent(
        name="active_storm_response",
        description="Parallel response: update resources and generate alerts simultaneously.",
        sub_agents=[
            _build_resource_agent(),
            _build_alert_agent(),
        ],
    )

    return SequentialAgent(
        name="active_storm_pipeline",
        description="Active storm pipeline: process reports, score severity, then respond in parallel.",
        sub_agents=[
            _build_field_report_agent(),
            _build_severity_agent(),
            response_parallel,
        ],
    )


def _build_post_storm_pipeline() -> ParallelAgent:
    """Post-storm: [Reunification + Resource] (parallel)."""
    return ParallelAgent(
        name="post_storm_pipeline",
        description="Post-storm pipeline: reunify families and manage resources in parallel.",
        sub_agents=[
            _build_reunification_agent(),
            _build_resource_agent(),
        ],
    )


async def run_orchestrator(phase_override: str | None = None) -> dict[str, Any]:
    """Run the appropriate agent pipeline for the current disaster phase.

    Args:
        phase_override: Optional phase to run instead of the DB phase.

    Returns:
        dict with status, phase, and agent summary.
    """
    if GROQ_API_KEY:
        os.environ.setdefault("GROQ_API_KEY", GROQ_API_KEY)
    if GEMINI_API_KEY:
        os.environ.setdefault("GOOGLE_API_KEY", GEMINI_API_KEY)

    phase = phase_override or _get_current_phase()

    if phase == "pre_storm":
        pipeline = _build_pre_storm_pipeline()
        prompt = (
            "Execute the pre-storm pipeline: First analyze NOAA weather data and "
            "compute risk assessments for all Tampa Bay neighborhoods, then generate "
            "appropriate evacuation and preparation alerts."
        )
    elif phase == "active_storm":
        pipeline = _build_active_storm_pipeline()
        prompt = (
            "Execute the active storm pipeline: Process all unprocessed field reports, "
            "rank incidents by severity, then simultaneously update resource statuses "
            "and generate emergency alerts."
        )
    elif phase == "post_storm":
        pipeline = _build_post_storm_pipeline()
        prompt = (
            "Execute the post-storm pipeline: Simultaneously run reunification matching "
            "for missing persons and update resource availability."
        )
    else:
        return {"status": "error", "error": f"Unknown phase: {phase}"}

    session_service = InMemorySessionService()
    runner = Runner(
        agent=pipeline,
        app_name=APP_NAME,
        session_service=session_service,
    )

    user_id = "aegis_system"
    session_id = f"orchestrator_{phase}_{uuid.uuid4().hex[:8]}"

    session = await session_service.create_session(
        app_name=APP_NAME,
        user_id=user_id,
        session_id=session_id,
    )

    user_message = types.Content(
        role="user",
        parts=[types.Part(text=prompt)],
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
        logger.error("Orchestrator error for phase %s: %s", phase, e)
        return {"status": "error", "phase": phase, "error": str(e)}

    return {
        "status": "success",
        "phase": phase,
        "pipeline": pipeline.name,
        "summary": final_text,
    }
