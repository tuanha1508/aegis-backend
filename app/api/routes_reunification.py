from fastapi import APIRouter

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
    from app.agents.reunification_agent import run_reunification_agent

    result = await run_reunification_agent()
    return result
