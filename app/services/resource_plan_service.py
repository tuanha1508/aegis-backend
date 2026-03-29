"""Rank nearby open resources for evacuation / supply planning."""

from __future__ import annotations

import json
import logging
from typing import Any

from app.config import GEMINI_API_KEY
from app.db.database import get_connection
from app.services.geo_match import haversine_m
from app.services.resource_discovery_service import ALLOWED_RESOURCE_TYPES

logger = logging.getLogger(__name__)

_MILES_PER_M = 1 / 1609.344
_TOP_PER_TYPE = 5
_GEMINI_MODEL = "gemini-2.5-flash"


def _distance_miles(
    lat1: float, lng1: float, lat2: float, lng2: float
) -> float:
    return haversine_m(lat1, lng1, lat2, lng2) * _MILES_PER_M


def build_resource_plan(
    lat: float,
    lng: float,
    needs: list[str],
    max_miles: float = 25.0,
) -> dict[str, Any]:
    """Return structured recommendations (no LLM)."""
    invalid = [n for n in needs if n not in ALLOWED_RESOURCE_TYPES]
    if invalid:
        raise ValueError(f"Unknown resource types: {invalid}. Allowed: {sorted(ALLOWED_RESOURCE_TYPES)}")

    conn = get_connection()
    try:
        placeholders = ",".join(["%s"] * len(needs))
        rows = conn.execute(
            f"""
            SELECT * FROM resources
            WHERE status IN ('open', 'limited')
              AND type IN ({placeholders})
            """,
            needs,
        ).fetchall()
    finally:
        conn.close()

    by_type: dict[str, list[tuple[float, dict[str, Any]]]] = {n: [] for n in needs}
    for row in rows:
        r = dict(row)
        d = _distance_miles(lat, lng, float(r["lat"]), float(r["lng"]))
        if d <= max_miles:
            by_type[r["type"]].append((d, r))

    recommendations: list[dict[str, Any]] = []
    for need in needs:
        ranked = sorted(by_type[need], key=lambda x: x[0])[:_TOP_PER_TYPE]
        for d_mi, r in ranked:
            recommendations.append(
                {
                    "id": r["id"],
                    "name": r["name"],
                    "type": r["type"],
                    "lat": float(r["lat"]),
                    "lng": float(r["lng"]),
                    "distance_miles": round(d_mi, 2),
                    "status": r["status"],
                    "address": r.get("address"),
                    "amenities": r.get("amenities"),
                }
            )

    return {
        "origin": {"lat": lat, "lng": lng},
        "max_miles": max_miles,
        "needs": needs,
        "recommendations": recommendations,
    }


def maybe_narrative(plan: dict[str, Any]) -> str | None:
    """Optional 2–3 sentence summary via Gemini."""
    if not GEMINI_API_KEY:
        return None
    try:
        from google import genai
    except ImportError:
        return None

    prompt = (
        "You help Tampa Bay residents during disasters. Given this JSON plan of nearby "
        "resources, write 2-3 short sentences in plain English: what to prioritize and that "
        "distances are approximate. Do not invent facilities not in the data.\n\n"
        f"{json.dumps(plan, ensure_ascii=False)[:8000]}"
    )
    try:
        client = genai.Client(api_key=GEMINI_API_KEY)
        resp = client.models.generate_content(model=_GEMINI_MODEL, contents=prompt)
        return (resp.text or "").strip() or None
    except Exception as ex:
        logger.warning("resource plan narrative failed: %s", ex)
        return None
