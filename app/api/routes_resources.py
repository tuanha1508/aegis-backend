import json
import math
import re
from typing import Optional
from uuid import uuid4

import httpx
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel
from psycopg import sql

from app.agents.resource_agent import run_resource_sync
from app.config import DEMO_MODE
from app.db.audit import insert_audit_log
from app.db.database import get_connection
from app.models.resource import ResourcePlanRequest, ResourcePlanResponse, ResourceUpdate
from app.services.resource_plan_service import build_resource_plan, maybe_narrative

router = APIRouter(tags=["resources"])


@router.post("/resources/sync")
async def sync_resources():
    run_id = uuid4()
    conn = get_connection()
    try:
        row = conn.execute("SELECT current_phase FROM phase WHERE id = 1").fetchone()
        phase = row["current_phase"] if row else None
        try:
            result = run_resource_sync(conn, run_id=run_id)
        except (httpx.HTTPError, json.JSONDecodeError) as exc:
            insert_audit_log(
                conn,
                agent_name="resource_agent",
                run_id=run_id,
                phase=phase,
                input_payload={
                    "trigger": "POST /resources/sync",
                    "demo_mode": DEMO_MODE,
                },
                output_payload={"status": "error"},
                error_message=type(exc).__name__,
            )
            conn.commit()
            raise HTTPException(
                status_code=503,
                detail="Resource discovery service unavailable. Try again later.",
            ) from exc
        insert_audit_log(
            conn,
            agent_name="resource_agent",
            run_id=run_id,
            phase=phase,
            input_payload={
                "trigger": "POST /resources/sync",
                "demo_mode": DEMO_MODE,
            },
            output_payload=result,
        )
        conn.commit()
        return {**result, "run_id": str(run_id), "status": "ok"}
    finally:
        conn.close()


@router.post("/resources/plan", response_model=ResourcePlanResponse)
async def plan_resources(body: ResourcePlanRequest):
    """Suggest nearby open/limited resources by type for evacuation or supplies."""
    try:
        plan = build_resource_plan(
            body.lat, body.lng, body.needs, max_miles=body.max_miles
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    narrative = maybe_narrative(plan)
    return ResourcePlanResponse(
        origin=plan["origin"],
        max_miles=plan["max_miles"],
        needs=plan["needs"],
        recommendations=plan["recommendations"],
        narrative=narrative,
    )


@router.get("/resources")
async def get_resources(type: Optional[str] = Query(None)):
    conn = get_connection()
    try:
        if type:
            rows = conn.execute(
                "SELECT * FROM resources WHERE type = %s ORDER BY name", (type,)
            ).fetchall()
        else:
            rows = conn.execute("SELECT * FROM resources ORDER BY name").fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


@router.get("/resources/nearest")
async def get_nearest_resource(
    lat: float = Query(...),
    lng: float = Query(...),
    type: Optional[str] = Query(None),
):
    conn = get_connection()
    try:
        if type:
            rows = conn.execute(
                "SELECT * FROM resources WHERE type = %s AND status = 'open'",
                (type,),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM resources WHERE status = 'open'"
            ).fetchall()

        if not rows:
            return {"resource": None, "distance_miles": None}

        def haversine(lat1, lng1, lat2, lng2):
            R = 3959
            dlat = math.radians(lat2 - lat1)
            dlng = math.radians(lng2 - lng1)
            a = (
                math.sin(dlat / 2) ** 2
                + math.cos(math.radians(lat1))
                * math.cos(math.radians(lat2))
                * math.sin(dlng / 2) ** 2
            )
            return R * 2 * math.asin(math.sqrt(a))

        nearest = min(rows, key=lambda r: haversine(lat, lng, r["lat"], r["lng"]))
        dist = haversine(lat, lng, nearest["lat"], nearest["lng"])
        return {"resource": dict(nearest), "distance_miles": round(dist, 2)}
    finally:
        conn.close()


class ResourceTextReport(BaseModel):
    text: str


def _normalize_for_match(name: str) -> str:
    s = name.lower()
    s = re.sub(r"[^a-z0-9\s]", " ", s)
    return " ".join(s.split())


def _fuzzy_match_resource(conn, parsed_name: str) -> dict | None:
    """Find the best existing resource matching the parsed name."""
    rows = conn.execute("SELECT * FROM resources").fetchall()
    norm = _normalize_for_match(parsed_name)
    if len(norm) < 3:
        return None
    for row in rows:
        row_norm = _normalize_for_match(row["name"])
        if norm in row_norm or row_norm in norm:
            return row
        words_a, words_b = set(norm.split()), set(row_norm.split())
        if words_a and words_b and len(words_a & words_b) >= min(2, min(len(words_a), len(words_b))):
            return row
    return None


@router.post("/resources/report-text")
async def report_resource_text(body: ResourceTextReport):
    """Parse free-form text into a resource update using Gemini.

    Example inputs:
      - "Tampa Convention Center has room for 200 more people"
      - "Middleton High shelter is at capacity, turning people away"
      - "New supply point opened at Temple Terrace Community Center with water and food"
    """
    if not body.text.strip():
        raise HTTPException(status_code=400, detail="text is required")

    from app.services.text_parser import parse_resource_text

    parsed = parse_resource_text(body.text)

    conn = get_connection()
    try:
        existing = _fuzzy_match_resource(conn, parsed.get("name", ""))

        if existing and not parsed.get("is_new"):
            set_parts: list = []
            params: list = []
            if parsed.get("status"):
                set_parts.append(sql.SQL("status = {}").format(sql.Placeholder()))
                params.append(parsed["status"])
            if parsed.get("current_occupancy") is not None:
                set_parts.append(sql.SQL("current_occupancy = {}").format(sql.Placeholder()))
                params.append(parsed["current_occupancy"])
            if parsed.get("amenities"):
                set_parts.append(sql.SQL("amenities = {}").format(sql.Placeholder()))
                params.append(parsed["amenities"])
            if parsed.get("capacity") is not None:
                set_parts.append(sql.SQL("capacity = {}").format(sql.Placeholder()))
                params.append(parsed["capacity"])

            if set_parts:
                set_parts.append(sql.SQL("last_updated = NOW()"))
                query = sql.SQL("UPDATE resources SET {} WHERE id = {}").format(
                    sql.SQL(", ").join(set_parts),
                    sql.Placeholder(),
                )
                params.append(existing["id"])
                conn.execute(query, params)

            conn.commit()
            row = conn.execute(
                "SELECT * FROM resources WHERE id = %s", (existing["id"],)
            ).fetchone()
            return {"status": "updated", "parsed": parsed, "record": dict(row)}
        else:
            row = conn.execute(
                """INSERT INTO resources
                   (type, name, lat, lng, capacity, current_occupancy, amenities, status)
                   VALUES (%s, %s, %s, %s, %s, %s, %s, %s) RETURNING *""",
                (
                    parsed.get("type", "shelter"),
                    parsed.get("name", "Unknown"),
                    parsed.get("lat", 27.95),
                    parsed.get("lng", -82.46),
                    parsed.get("capacity"),
                    parsed.get("current_occupancy"),
                    parsed.get("amenities"),
                    parsed.get("status", "open"),
                ),
            ).fetchone()
            conn.commit()
            return {"status": "created", "parsed": parsed, "record": dict(row)}
    finally:
        conn.close()


@router.put("/resources/{resource_id}")
async def update_resource(resource_id: int, update: ResourceUpdate):
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT * FROM resources WHERE id = %s", (resource_id,)
        ).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Resource not found")

        set_parts: list = []
        params: list = []
        if update.status is not None:
            set_parts.append(sql.SQL("status = {}").format(sql.Placeholder()))
            params.append(update.status)
        if update.current_occupancy is not None:
            set_parts.append(
                sql.SQL("current_occupancy = {}").format(sql.Placeholder())
            )
            params.append(update.current_occupancy)
        if update.notes is not None:
            set_parts.append(sql.SQL("notes = {}").format(sql.Placeholder()))
            params.append(update.notes)

        if set_parts:
            set_parts.append(sql.SQL("last_updated = NOW()"))
            query = sql.SQL("UPDATE resources SET {} WHERE id = {}").format(
                sql.SQL(", ").join(set_parts),
                sql.Placeholder(),
            )
            params.append(resource_id)
            conn.execute(query, params)
            conn.commit()

        row = conn.execute(
            "SELECT * FROM resources WHERE id = %s", (resource_id,)
        ).fetchone()
        return dict(row)
    finally:
        conn.close()
