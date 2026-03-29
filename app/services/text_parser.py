"""Gemini-powered free-text parsing for reunification and resource reports.

Uses a single ``google.genai`` call with a JSON-schema prompt so latency
stays under ~2 s (no ADK overhead).  Falls back to Groq via LiteLLM when
``GROQ_API_KEY`` is set — same pattern as the other agents.
"""

from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import Any

from app.config import GEMINI_API_KEY, GROQ_API_KEY

logger = logging.getLogger(__name__)

_DATA_DIR = Path(__file__).resolve().parent.parent / "data"

_GEMINI_MODEL = "gemini-2.0-flash"


def _load_reference_locations() -> str:
    """Build a compact reference string of Tampa shelters + neighborhoods."""
    lines: list[str] = []
    with open(_DATA_DIR / "tampa_shelters.json") as f:
        shelters = json.load(f)
    for s in shelters:
        lines.append(f"- {s['name']} ({s['type']}) lat={s['lat']} lng={s['lng']}")
    with open(_DATA_DIR / "tampa_zones.json") as f:
        zones = json.load(f)
    for z in zones:
        lines.append(f"- {z['neighborhood']} (zone {z['zone']}) lat={z['lat']} lng={z['lng']}")
    return "\n".join(lines)


def _strip_json_fence(text: str) -> str:
    t = text.strip()
    if t.startswith("```"):
        t = re.sub(r"^```\w*\n?", "", t)
        t = re.sub(r"\n?```\s*$", "", t)
    return t.strip()


def _call_llm(prompt: str) -> str:
    """Call Gemini (or Groq via LiteLLM) and return the raw text response."""
    if GROQ_API_KEY:
        import litellm
        resp = litellm.completion(
            model="groq/llama-3.3-70b-versatile",
            messages=[{"role": "user", "content": prompt}],
            api_key=GROQ_API_KEY,
            temperature=0.1,
        )
        return resp.choices[0].message.content or ""

    from google import genai
    client = genai.Client(api_key=GEMINI_API_KEY)
    resp = client.models.generate_content(model=_GEMINI_MODEL, contents=prompt)
    return resp.text or ""


def parse_person_text(text: str) -> dict[str, Any]:
    """Parse free-form text into a structured found-or-missing person record.

    Returns a dict with keys:
        type ("found" | "missing"), name, age_approx, gender, description,
        location (found_at or last_known_location), lat, lng
    """
    ref = _load_reference_locations()
    prompt = (
        "You extract structured person data from disaster reports for Tampa Bay.\n\n"
        "REFERENCE LOCATIONS (use for geocoding):\n"
        f"{ref}\n\n"
        "INPUT TEXT:\n"
        f'"{text}"\n\n'
        "OUTPUT: Return ONLY a JSON object (no markdown fences) with these fields:\n"
        '- "type": "found" if the person has been located/seen/checked-in, "missing" if someone is reporting a person missing\n'
        '- "name": string (the person\'s name, or "Unknown" if not mentioned)\n'
        '- "age_approx": int or null\n'
        '- "gender": "male", "female", or null\n'
        '- "description": string (physical description, clothing, distinguishing features)\n'
        '- "location": string (shelter name or area where found/last seen)\n'
        '- "lat": float (from reference locations above)\n'
        '- "lng": float (from reference locations above)\n\n'
        "Match location mentions to the nearest reference location for lat/lng. "
        "If no location is mentioned, use lat=27.95, lng=-82.46 (downtown Tampa)."
    )
    raw = _call_llm(prompt)
    try:
        return json.loads(_strip_json_fence(raw))
    except (json.JSONDecodeError, TypeError):
        logger.error("Failed to parse person text LLM response: %s", raw[:300])
        return {
            "type": "found",
            "name": "Unknown",
            "age_approx": None,
            "gender": None,
            "description": text,
            "location": "Tampa Bay Area",
            "lat": 27.95,
            "lng": -82.46,
        }


def parse_resource_text(text: str) -> dict[str, Any]:
    """Parse free-form text into a structured resource update.

    Returns a dict with keys:
        name, type (shelter|supply_point|medical|charging),
        capacity, current_occupancy, amenities, status (open|limited|full|closed),
        lat, lng, is_new (bool — true if this seems like a brand-new resource)
    """
    ref = _load_reference_locations()
    prompt = (
        "You extract structured resource updates from disaster reports for Tampa Bay.\n\n"
        "EXISTING RESOURCES (match by name if possible):\n"
        f"{ref}\n\n"
        "INPUT TEXT:\n"
        f'"{text}"\n\n'
        "OUTPUT: Return ONLY a JSON object (no markdown fences) with these fields:\n"
        '- "name": string (resource/facility name — match to an existing resource above if possible)\n'
        '- "type": one of "shelter", "supply_point", "medical", "charging"\n'
        '- "capacity": int or null (total capacity if mentioned)\n'
        '- "current_occupancy": int or null (current number of people if mentioned)\n'
        '- "amenities": string or null (comma-separated: hot_meals,charging,pet_friendly,wifi,medical_station)\n'
        '- "status": one of "open", "limited", "full", "closed"\n'
        '- "lat": float (from reference locations above)\n'
        '- "lng": float (from reference locations above)\n'
        '- "is_new": boolean (true only if this is clearly a brand-new resource not in the list above)\n\n'
        "Infer status from context: 'at capacity'/'full'→'full', 'running low'→'limited', "
        "'closed'/'shut down'→'closed', otherwise 'open'. "
        "If the text mentions available spots, calculate current_occupancy = capacity - available."
    )
    raw = _call_llm(prompt)
    try:
        return json.loads(_strip_json_fence(raw))
    except (json.JSONDecodeError, TypeError):
        logger.error("Failed to parse resource text LLM response: %s", raw[:300])
        return {
            "name": "Unknown Resource",
            "type": "shelter",
            "capacity": None,
            "current_occupancy": None,
            "amenities": None,
            "status": "open",
            "lat": 27.95,
            "lng": -82.46,
            "is_new": True,
        }
