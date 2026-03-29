"""Discover Tampa-area shelters / supply points and upsert into resources."""

from __future__ import annotations

import json
import math
import re
from typing import Any
from uuid import UUID, uuid4

import psycopg

from app.config import DEMO_MODE, GEMINI_API_KEY, GROQ_API_KEY
from app.db.database import get_connection
from app.services.resource_discovery_service import (
    ALLOWED_RESOURCE_TYPES,
    ResourceCandidate,
    discover_candidates,
)

_GEMINI_MODEL = "gemini-2.0-flash"


def haversine_m(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    r = 6_371_000.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lng2 - lng1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(min(1.0, math.sqrt(a)))


def _normalize_name(name: str) -> str:
    s = name.lower()
    s = re.sub(r"[^a-z0-9\s]", " ", s)
    return " ".join(s.split())


def _names_match(a: str, b: str) -> bool:
    na, nb = _normalize_name(a), _normalize_name(b)
    if len(na) < 2 or len(nb) < 2:
        return False
    if na in nb or nb in na:
        return True
    wa, wb = set(na.split()), set(nb.split())
    if not wa or not wb:
        return False
    inter = len(wa & wb)
    return inter >= min(2, min(len(wa), len(wb)))


def _osm_token(osm_type: str, osm_id: int) -> str:
    return f"| osm:{osm_type}/{osm_id}"


def _find_by_osm(conn: psycopg.Connection, osm_type: str, osm_id: int) -> dict | None:
    token = _osm_token(osm_type, osm_id)
    return conn.execute(
        "SELECT * FROM resources WHERE notes LIKE %s",
        (f"%{token}%",),
    ).fetchone()


def _find_fuzzy(
    conn: psycopg.Connection,
    candidate: ResourceCandidate,
    max_m: float = 100.0,
) -> dict | None:
    rows = conn.execute(
        "SELECT * FROM resources WHERE type = %s",
        (candidate.type,),
    ).fetchall()
    best: dict | None = None
    best_d = max_m + 1.0
    for row in rows:
        d = haversine_m(
            candidate.lat,
            candidate.lng,
            float(row["lat"]),
            float(row["lng"]),
        )
        if d <= max_m and _names_match(candidate.name, row["name"]):
            if d < best_d:
                best_d = d
                best = row
    return best


def _resolve_row(conn: psycopg.Connection, c: ResourceCandidate) -> dict | None:
    if c.osm_type and c.osm_id is not None:
        row = _find_by_osm(conn, c.osm_type, c.osm_id)
        if row:
            return row
    return _find_fuzzy(conn, c)


def _strip_json_fence(text: str) -> str:
    t = text.strip()
    if t.startswith("```"):
        t = re.sub(r"^```\w*\n?", "", t)
        t = re.sub(r"\n?```\s*$", "", t)
    return t.strip()


def _apply_gemini_normalization(candidates: list[ResourceCandidate]) -> None:
    if not GEMINI_API_KEY or not candidates:
        return
    try:
        from google import genai
    except ImportError:
        return
    items = [
        {
            "i": i,
            "name": c.name,
            "type_guess": c.type,
            "amenities": c.amenities or "",
            "tags": c.raw_tags,
        }
        for i, c in enumerate(candidates)
    ]
    prompt = (
        "You normalize disaster resource records for a Tampa Bay database.\n"
        "Given JSON input with objects having i, name, type_guess, amenities, tags — "
        "output ONLY a JSON array of objects {\"i\": int, \"type\": one of "
        "shelter,medical,supply_point,charging,road, \"amenities\": string}.\n"
        "amenities: short comma-separated keywords (e.g. hot_meals,wheelchair,food_bank). "
        "Use type_guess unless tags clearly indicate another allowed type.\n\n"
        f"INPUT:\n{json.dumps(items, ensure_ascii=False)}"
    )
    try:
        client = genai.Client(api_key=GEMINI_API_KEY)
        resp = client.models.generate_content(model=_GEMINI_MODEL, contents=prompt)
        text = resp.text or ""
        data = json.loads(_strip_json_fence(text))
        if not isinstance(data, list):
            return
        by_i = {entry.get("i"): entry for entry in data if isinstance(entry, dict)}
        for i, c in enumerate(candidates):
            entry = by_i.get(i)
            if not entry:
                continue
            t = entry.get("type")
            av = entry.get("amenities")
            if isinstance(t, str) and t in ALLOWED_RESOURCE_TYPES:
                c.type = t
            if isinstance(av, str) and av.strip():
                c.amenities = av.strip()
    except Exception:
        return


def run_resource_sync(conn: psycopg.Connection, *, run_id: UUID | None = None) -> dict[str, Any]:
    """
    Fetch discovery candidates, optionally normalize with Gemini, upsert into resources.
    Does not commit — caller commits.
    Preserves existing status, current_occupancy, and notes on UPDATE.
    """
    _ = run_id
    candidates, source = discover_candidates()
    _apply_gemini_normalization(candidates)

    inserted = 0
    updated = 0
    errors: list[str] = []

    for c in candidates:
        if c.type not in ALLOWED_RESOURCE_TYPES:
            continue
        try:
            existing = _resolve_row(conn, c)
            if existing:
                conn.execute(
                    """
                    UPDATE resources
                    SET name = %s,
                        lat = %s,
                        lng = %s,
                        address = %s,
                        amenities = %s,
                        capacity = COALESCE(%s, capacity),
                        last_updated = NOW()
                    WHERE id = %s
                    """,
                    (
                        c.name,
                        c.lat,
                        c.lng,
                        c.address,
                        c.amenities,
                        c.capacity,
                        existing["id"],
                    ),
                )
                updated += 1
            else:
                notes_val: str | None = None
                if c.osm_type and c.osm_id is not None:
                    notes_val = _osm_token(c.osm_type, c.osm_id).strip()
                conn.execute(
                    """
                    INSERT INTO resources
                        (type, name, lat, lng, address, capacity, amenities, status, notes)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, 'open', %s)
                    """,
                    (
                        c.type,
                        c.name,
                        c.lat,
                        c.lng,
                        c.address,
                        c.capacity,
                        c.amenities,
                        notes_val,
                    ),
                )
                inserted += 1
        except Exception as ex:
            errors.append(f"{c.name}: {ex}")

    return {
        "inserted": inserted,
        "updated": updated,
        "errors": errors,
        "source": source,
        "demo_mode": DEMO_MODE,
        "candidates_seen": len(candidates),
    }


def _get_model():
    from google.adk.models.lite_llm import LiteLlm

    if GROQ_API_KEY:
        return LiteLlm(model="groq/llama-3.3-70b-versatile")
    return "gemini-2.0-flash"


def sync_discovered_resources() -> dict[str, Any]:
    """ADK tool: upsert shelters/supply points from discovery (demo JSON or Overpass)."""
    conn = get_connection()
    rid = uuid4()
    try:
        result = run_resource_sync(conn, run_id=rid)
        conn.commit()
        return result
    finally:
        conn.close()


def _build_resource_agent():
    from google.adk.agents import Agent

    return Agent(
        name="resource_agent",
        model=_get_model(),
        description="Syncs discovered shelter and supply-point data into the resources table.",
        instruction=(
            "When asked to refresh resources, sync discovery, or update the resource database, "
            "call sync_discovered_resources() once and summarize inserted/updated counts briefly."
        ),
        tools=[sync_discovered_resources],
    )
