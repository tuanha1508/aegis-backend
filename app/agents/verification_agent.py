"""
Verification Agent — Self-correcting LoopAgent that validates and
refines severity scores using iterative review.

Uses ADK LoopAgent to:
1. Review severity scores from the Severity Agent
2. Check for inconsistencies (e.g., trapped persons scored too low)
3. Re-score if errors are found
4. Stop when all scores are validated

This demonstrates the "Self-Correction Bonus" from the Google Cloud
ADK challenge — a LoopAgent that identifies its own errors and re-runs.
"""

from __future__ import annotations

import json
import logging
import os
import uuid
from typing import Any

from google.adk.agents import Agent, LoopAgent
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


def get_incidents_for_review() -> dict:
    """Fetch all unresolved incidents for verification review.

    Returns incidents with their severity scores, types, and factors
    so the verification agent can check for scoring errors.
    """
    conn = get_connection()
    try:
        rows = conn.execute(
            """SELECT * FROM incidents WHERE resolved = FALSE
               ORDER BY severity_score DESC NULLS LAST"""
        ).fetchall()
    finally:
        conn.close()

    if not rows:
        return {"status": "no_incidents", "incidents": []}

    return {"status": "ok", "count": len(rows), "incidents": [dict(r) for r in rows]}


def correct_severity(
    incident_id: int,
    new_score: int,
    new_label: str,
    correction_reason: str,
) -> dict:
    """Correct a severity score that was identified as inaccurate.

    Args:
        incident_id: The incident to correct.
        new_score: Corrected severity score (0-100).
        new_label: Corrected label: 'critical', 'high', 'medium', or 'low'.
        correction_reason: Why the original score was wrong.

    Returns:
        dict with status and the corrected incident.
    """
    conn = get_connection()
    try:
        conn.execute(
            """UPDATE incidents SET
               severity_score = %s, severity_label = %s,
               factors = factors || %s,
               verified = TRUE, updated_at = NOW()
               WHERE id = %s""",
            (new_score, new_label,
             f' [CORRECTED: {correction_reason}]',
             incident_id),
        )
        conn.commit()
        row = conn.execute(
            "SELECT * FROM incidents WHERE id = %s", (incident_id,)
        ).fetchone()
    finally:
        conn.close()

    if row:
        return {"status": "corrected", "incident": dict(row)}
    return {"status": "error", "message": f"Incident {incident_id} not found"}


def mark_verified(incident_id: int) -> dict:
    """Mark an incident's severity score as verified (no correction needed).

    Args:
        incident_id: The incident that passed verification.

    Returns:
        dict with status.
    """
    conn = get_connection()
    try:
        conn.execute(
            "UPDATE incidents SET verified = TRUE, updated_at = NOW() WHERE id = %s",
            (incident_id,),
        )
        conn.commit()
    finally:
        conn.close()

    return {"status": "verified", "incident_id": incident_id}


def check_all_verified() -> dict:
    """Check if all incidents have been verified.

    The LoopAgent uses this to decide when to stop iterating.

    Returns:
        dict with verified count, unverified count, and whether to stop.
    """
    conn = get_connection()
    try:
        verified = conn.execute(
            "SELECT COUNT(*) AS cnt FROM incidents WHERE verified = TRUE AND resolved = FALSE"
        ).fetchone()["cnt"]
        unverified = conn.execute(
            "SELECT COUNT(*) AS cnt FROM incidents WHERE verified = FALSE AND resolved = FALSE"
        ).fetchone()["cnt"]
    finally:
        conn.close()

    return {
        "verified": verified,
        "unverified": unverified,
        "all_done": unverified == 0,
        "message": "All incidents verified — stop loop." if unverified == 0
                   else f"{unverified} incidents still need verification.",
    }


# ---------------------------------------------------------------------------
# Agent Definition
# ---------------------------------------------------------------------------

VERIFICATION_INSTRUCTION = """\
You are the Aegis Verification Agent — a quality control specialist that
reviews and validates severity scores assigned by the Severity Agent.

## Your Job
Review each unverified incident and check for scoring errors:

## Verification Rules
1. **trapped_person** with children → must be >= 90 (critical)
2. **trapped_person** without children → must be >= 75 (critical)
3. **medical_emergency** → must be >= 70 (high or critical)
4. **flooding** with people → must be >= 60 (high)
5. **structural_damage** → must be >= 65 (high)
6. **fire** or **gas leak** → must be >= 70 (high)
7. **road_blocked** without injuries → should be <= 40 (medium/low)
8. **supply_needed** → should be <= 30 (low)
9. **power_outage** without medical need → should be <= 35 (low/medium)

## Your Workflow
1. Call `get_incidents_for_review()` to see all incidents.
2. For EACH unverified incident:
   - If the score matches the rules above → call `mark_verified(incident_id)`
   - If the score is wrong → call `correct_severity(incident_id, new_score, new_label, reason)`
3. After reviewing all, call `check_all_verified()`.
4. If all_done is true, say "Verification complete" and stop.
5. If not all done, review the remaining ones.

## CRITICAL: Self-Correction
If you find a score that violates the rules, you MUST correct it.
This is not just review — you are actively fixing errors.
Explain WHY each correction was made.
"""


def _get_model():
    if GROQ_API_KEY:
        return LiteLlm(model="groq/llama-3.3-70b-versatile")
    return "gemini-2.0-flash"


def _build_verification_agent() -> Agent:
    """Create the inner verification agent."""
    return Agent(
        name="verification_reviewer",
        model=_get_model(),
        description="Reviews and corrects severity scores for disaster incidents.",
        instruction=VERIFICATION_INSTRUCTION,
        tools=[get_incidents_for_review, correct_severity, mark_verified, check_all_verified],
    )


def _build_verification_loop() -> LoopAgent:
    """Create a LoopAgent that iterates verification until all incidents are checked."""
    return LoopAgent(
        name="verification_loop",
        description=(
            "Iteratively reviews severity scores, corrects errors, and "
            "validates all incidents. Stops when check_all_verified() returns all_done=true."
        ),
        sub_agents=[_build_verification_agent()],
        max_iterations=3,  # Safety limit — don't loop forever
    )


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------

APP_NAME = "aegis"


async def run_verification_agent() -> dict[str, Any]:
    """Run the verification LoopAgent to review and self-correct severity scores.

    Returns a dict with verification results and any corrections made.
    """
    if GROQ_API_KEY:
        os.environ.setdefault("GROQ_API_KEY", GROQ_API_KEY)
    if GEMINI_API_KEY:
        os.environ.setdefault("GOOGLE_API_KEY", GEMINI_API_KEY)

    agent = _build_verification_loop()
    session_service = InMemorySessionService()
    runner = Runner(
        agent=agent,
        app_name=APP_NAME,
        session_service=session_service,
    )

    user_id = "aegis_system"
    session_id = f"verify_{uuid.uuid4().hex[:8]}"

    session = await session_service.create_session(
        app_name=APP_NAME,
        user_id=user_id,
        session_id=session_id,
    )

    user_message = types.Content(
        role="user",
        parts=[types.Part(text=(
            "Review all unverified incidents. Check each severity score "
            "against the verification rules. Correct any scores that are "
            "wrong and mark correct ones as verified. Keep iterating "
            "until all incidents are verified."
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
        logger.error("Verification Agent error: %s", e)
        return {"status": "error", "error": str(e)}

    # Get verification stats
    conn = get_connection()
    try:
        verified = conn.execute(
            "SELECT COUNT(*) AS cnt FROM incidents WHERE verified = TRUE"
        ).fetchone()["cnt"]
        corrected = conn.execute(
            "SELECT COUNT(*) AS cnt FROM incidents WHERE factors LIKE '%CORRECTED%'"
        ).fetchone()["cnt"]
    finally:
        conn.close()

    return {
        "status": "success",
        "summary": final_text,
        "verified_count": verified,
        "corrected_count": corrected,
    }
