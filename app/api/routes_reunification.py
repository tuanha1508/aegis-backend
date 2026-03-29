from typing import Any
from uuid import uuid4

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.db.audit import insert_audit_log
from app.db.database import get_connection
from app.models.person import (
    MissingPersonCreate,
    MissingPersonResponse,
    FoundPersonCreate,
    FoundPersonResponse,
)

router = APIRouter(tags=["reunification"])


@router.get("/reunification/missing")
async def get_missing():
    conn = get_connection()
    try:
        rows = conn.execute(
            "SELECT * FROM missing_persons ORDER BY created_at DESC"
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


@router.post("/reunification/missing", response_model=MissingPersonResponse)
async def report_missing(person: MissingPersonCreate):
    conn = get_connection()
    try:
        row = conn.execute(
            """INSERT INTO missing_persons
               (reported_by, reporter_phone, name, age, gender, description,
                last_known_location, last_known_lat, last_known_lng, last_contact)
               VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s) RETURNING *""",
            (
                person.reported_by,
                person.reporter_phone,
                person.name,
                person.age,
                person.gender,
                person.description,
                person.last_known_location,
                person.last_known_lat,
                person.last_known_lng,
                person.last_contact,
            ),
        ).fetchone()
        conn.commit()
        return dict(row)
    finally:
        conn.close()


@router.get("/reunification/found")
async def get_found():
    conn = get_connection()
    try:
        rows = conn.execute(
            "SELECT * FROM found_persons ORDER BY checked_in DESC"
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


@router.post("/reunification/found", response_model=FoundPersonResponse)
async def report_found(person: FoundPersonCreate):
    conn = get_connection()
    try:
        row = conn.execute(
            """INSERT INTO found_persons
               (name, age_approx, gender, description, found_at, found_lat, found_lng)
               VALUES (%s, %s, %s, %s, %s, %s, %s) RETURNING *""",
            (
                person.name,
                person.age_approx,
                person.gender,
                person.description,
                person.found_at,
                person.found_lat,
                person.found_lng,
            ),
        ).fetchone()
        conn.commit()
        return dict(row)
    finally:
        conn.close()


@router.get("/reunification/matches")
async def get_matches():
    conn = get_connection()
    try:
        rows = conn.execute(
            "SELECT * FROM matches ORDER BY confidence DESC"
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


@router.post("/reunification/match")
async def trigger_matching():
    """Trigger the Reunification Agent to match missing persons with found persons."""
    run_id = uuid4()
    from app.agents.reunification_agent import run_reunification_agent

    result: Any = await run_reunification_agent()

    conn = get_connection()
    try:
        row = conn.execute("SELECT current_phase FROM phase WHERE id = 1").fetchone()
        phase = row["current_phase"] if row else None
        payload = result if isinstance(result, dict) else {"result": result}
        insert_audit_log(
            conn,
            agent_name="reunification_agent",
            run_id=run_id,
            phase=phase,
            input_payload={"trigger": "POST /reunification/match"},
            output_payload=payload,
        )
        conn.commit()
    finally:
        conn.close()

    return {**payload, "run_id": str(run_id)}


class MatchReview(BaseModel):
    status: str  # "confirmed" or "rejected"
    reviewed_by: str


@router.patch("/reunification/matches/{match_id}")
async def review_match(match_id: int, body: MatchReview):
    """Review a match — confirm or reject it."""
    if body.status not in ("confirmed", "rejected"):
        raise HTTPException(status_code=400, detail="Status must be 'confirmed' or 'rejected'")

    conn = get_connection()
    try:
        row = conn.execute("SELECT * FROM matches WHERE id = %s", (match_id,)).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Match not found")

        conn.execute(
            "UPDATE matches SET status = %s, reviewed_by = %s WHERE id = %s",
            (body.status, body.reviewed_by, match_id),
        )

        if body.status == "confirmed":
            conn.execute(
                "UPDATE missing_persons SET status = 'found' WHERE id = %s",
                (row["missing_id"],),
            )
            conn.execute(
                "UPDATE found_persons SET matched_missing_id = %s WHERE id = %s",
                (row["missing_id"], row["found_id"]),
            )

        conn.commit()
        updated = conn.execute("SELECT * FROM matches WHERE id = %s", (match_id,)).fetchone()
        return dict(updated)
    finally:
        conn.close()
