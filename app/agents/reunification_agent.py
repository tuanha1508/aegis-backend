"""
Reunification Agent — Matches missing persons with found persons.

Uses Google ADK + Gemini for fuzzy name matching, age/gender/description
comparison, and location plausibility analysis to produce match candidates
with confidence scores. Results are persisted to the matches table.
"""

from __future__ import annotations

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


def get_missing_persons() -> dict:
    """Fetch all missing person reports from the database.

    Returns:
        dict: List of missing persons with their names, ages, genders,
              physical descriptions, and last known locations.
    """
    conn = get_connection()
    rows = conn.execute(
        "SELECT * FROM missing_persons WHERE status = 'missing' ORDER BY created_at DESC"
    ).fetchall()
    conn.close()

    if not rows:
        return {"status": "no_data", "missing": []}

    return {"status": "ok", "count": len(rows), "missing": [dict(r) for r in rows]}


def get_found_persons() -> dict:
    """Fetch all found person records that haven't been matched yet.

    Returns:
        dict: List of found persons with their names, approximate ages,
              descriptions, and where they were found/checked in.
    """
    conn = get_connection()
    rows = conn.execute(
        "SELECT * FROM found_persons WHERE matched_missing_id IS NULL ORDER BY checked_in DESC"
    ).fetchall()
    conn.close()

    if not rows:
        return {"status": "no_data", "found": []}

    return {"status": "ok", "count": len(rows), "found": [dict(r) for r in rows]}


def save_match(
    missing_id: int,
    found_id: int,
    confidence: float,
    match_factors: str,
) -> dict:
    """Save a match between a missing person and a found person.

    Args:
        missing_id: Database ID of the missing person record.
        found_id: Database ID of the found person record.
        confidence: Match confidence score from 0.0 to 1.0.
                    Only save matches with confidence >= 0.5.
        match_factors: JSON string describing why this is a match.
                       e.g. '{"name_similarity": 0.9, "age_match": true,
                              "gender_match": true, "description_overlap": 0.8,
                              "location_plausible": true}'

    Returns:
        dict: Status and the saved match ID.
    """
    conn = get_connection()
    row = conn.execute(
        """INSERT INTO matches (missing_id, found_id, confidence, match_factors, status)
           VALUES (%s, %s, %s, %s, 'pending') RETURNING id""",
        (missing_id, found_id, confidence, match_factors),
    ).fetchone()

    # Update found_persons to link the match
    conn.execute(
        "UPDATE found_persons SET matched_missing_id = %s WHERE id = %s",
        (missing_id, found_id),
    )

    # If high confidence, update missing person status
    if confidence >= 0.8:
        conn.execute(
            "UPDATE missing_persons SET status = 'likely_found' WHERE id = %s",
            (missing_id,),
        )

    conn.commit()
    match_id = row["id"] if row else None
    conn.close()

    return {"status": "saved", "match_id": match_id}


# ---------------------------------------------------------------------------
# Agent Definition
# ---------------------------------------------------------------------------

REUNIFICATION_INSTRUCTION = """\
You are the Aegis Reunification Agent for Tampa Bay disaster response.

Your job is to match missing persons with found/shelter check-in records
by analyzing names, physical descriptions, ages, genders, and locations.

## Your Workflow

1. Call `get_missing_persons()` to get all missing person reports.
2. Call `get_found_persons()` to get all unmatched found person records.
3. For each missing person, compare against ALL found persons and compute
   a match confidence score.
4. Call `save_match()` for any pair with confidence >= 0.5.
5. Provide a summary of matches found.

## Matching Criteria & Scoring

### Name Similarity (0-35% of total)
- Exact full name match: 35%
- First name matches, last name abbreviated or similar: 25-30%
- Only first name matches: 15-20%
- Nickname or common variation: 10-15%
- No name overlap: 0%

### Age Match (0-15% of total)
- Exact age match: 15%
- Within 2 years: 12%
- Within 5 years: 8%
- Within 10 years: 5%
- More than 10 years off: 0%

### Gender Match (0-10% of total)
- Same gender: 10%
- Unknown/unspecified: 5%
- Different gender: 0%

### Physical Description (0-25% of total)
- Multiple matching features (hair, glasses, walker, clothing): 20-25%
- Some matching features: 10-15%
- One matching feature: 5%
- No description overlap: 0%

### Location Plausibility (0-15% of total)
- Found at a shelter near last known location (within 5 miles): 15%
- Found in the same general area of Tampa: 10%
- Found in Tampa but far from last known location: 5%
- Found outside Tampa Bay area: 0%

## Example: Maria Garcia → Maria G.
- Name: "Maria Garcia" vs "Maria G." — first name exact, last name abbreviated → ~28%
- Age: 72 vs ~70 — within 2 years → ~12%
- Gender: female vs female → 10%
- Description: "short gray hair, glasses, uses a walker" vs
  "elderly woman with walker, Spanish speaking" — walker matches, elderly
  matches age → ~22%
- Location: last seen Davis Islands, found at First Baptist Church (both Tampa,
  ~3 miles apart) → ~15%
- Total: ~87-89%

## CRITICAL RULES
- Compare EVERY missing person against EVERY found person.
- Only save matches with confidence >= 0.5 (50%).
- The confidence value must be between 0.0 and 1.0 (not 0-100).
- match_factors must be a valid JSON string explaining the scoring breakdown.
- Be generous but realistic — in disasters, people may look different than
  described (wet, disheveled, without glasses, etc.).
- Consider that names on found records may be incomplete, misspelled, or
  given as nicknames.
"""


def _get_model():
    """Use Gemini — Groq fails on save_match multi-param tool calls."""
    return "gemini-2.5-flash"


def _build_reunification_agent() -> Agent:
    """Create a fresh Reunification Agent instance."""
    return Agent(
        name="reunification_agent",
        model=_get_model(),
        description=(
            "Matches missing persons with found/shelter check-in records using "
            "fuzzy name matching, physical description comparison, and location "
            "plausibility analysis."
        ),
        instruction=REUNIFICATION_INSTRUCTION,
        tools=[get_missing_persons, get_found_persons, save_match],
    )


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------

APP_NAME = "aegis"


async def run_reunification_agent() -> dict[str, Any]:
    """Execute the Reunification Agent to find matches between missing and found persons.

    Returns a dict with:
        - status: "success" or "error"
        - summary: text summary from the agent
        - matches: list of matches from the DB
    """
    if GROQ_API_KEY:
        os.environ.setdefault("GROQ_API_KEY", GROQ_API_KEY)
    if GEMINI_API_KEY:
        os.environ.setdefault("GOOGLE_API_KEY", GEMINI_API_KEY)

    agent = _build_reunification_agent()
    session_service = InMemorySessionService()
    runner = Runner(
        agent=agent,
        app_name=APP_NAME,
        session_service=session_service,
    )

    user_id = "aegis_system"
    session_id = f"reunification_{uuid.uuid4().hex[:8]}"

    session = await session_service.create_session(
        app_name=APP_NAME,
        user_id=user_id,
        session_id=session_id,
    )

    user_message = types.Content(
        role="user",
        parts=[types.Part(text=(
            "Compare all missing persons against all found persons. Analyze names, "
            "ages, genders, physical descriptions, and locations to find potential "
            "matches. Save any match with confidence >= 50%. Provide a detailed "
            "summary of your findings."
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
        logger.error("Reunification Agent error: %s", e)
        return {"status": "error", "error": str(e), "matches": []}

    # Fetch matches from DB
    conn = get_connection()
    rows = conn.execute(
        "SELECT * FROM matches ORDER BY confidence DESC"
    ).fetchall()
    conn.close()

    matches = [dict(r) for r in rows]

    return {
        "status": "success",
        "summary": final_text,
        "matches": matches,
        "matches_count": len(matches),
    }
