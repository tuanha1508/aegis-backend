from typing import List, Optional

from fastapi import APIRouter, HTTPException, Query
from psycopg import sql

from app.db.database import get_connection
from app.models.assignment import (
    AssignmentCreate,
    AssignmentResponse,
    AssignmentStatusUpdate,
)

router = APIRouter(tags=["assignments"])


@router.get("/assignments", response_model=List[AssignmentResponse])
async def list_assignments(incident_id: Optional[int] = Query(None)):
    conn = get_connection()
    try:
        if incident_id is not None:
            rows = conn.execute(
                """SELECT * FROM assignments WHERE incident_id = %s
                   ORDER BY assigned_at DESC""",
                (incident_id,),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM assignments ORDER BY assigned_at DESC"
            ).fetchall()
        return [AssignmentResponse.model_validate(dict(r)) for r in rows]
    finally:
        conn.close()


@router.get("/assignments/{assignment_id}", response_model=AssignmentResponse)
async def get_assignment(assignment_id: int):
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT * FROM assignments WHERE id = %s", (assignment_id,)
        ).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Assignment not found")
        return AssignmentResponse.model_validate(dict(row))
    finally:
        conn.close()


@router.post("/assignments", response_model=AssignmentResponse)
async def create_assignment(body: AssignmentCreate):
    conn = get_connection()
    try:
        inc = conn.execute(
            "SELECT id FROM incidents WHERE id = %s", (body.incident_id,)
        ).fetchone()
        if not inc:
            raise HTTPException(status_code=404, detail="Incident not found")
        row = conn.execute(
            """INSERT INTO assignments
               (incident_id, recommended_action, assignee, notes)
               VALUES (%s, %s, %s, %s) RETURNING *""",
            (
                body.incident_id,
                body.recommended_action,
                body.assignee,
                body.notes,
            ),
        ).fetchone()
        conn.commit()
        return AssignmentResponse.model_validate(dict(row))
    finally:
        conn.close()


@router.patch("/assignments/{assignment_id}", response_model=AssignmentResponse)
async def update_assignment_status(assignment_id: int, body: AssignmentStatusUpdate):
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT * FROM assignments WHERE id = %s", (assignment_id,)
        ).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Assignment not found")

        set_parts: list = [sql.SQL("status = {}").format(sql.Placeholder())]
        params: list = [body.status]
        if body.assignee is not None:
            set_parts.append(sql.SQL("assignee = {}").format(sql.Placeholder()))
            params.append(body.assignee)
        if body.notes is not None:
            set_parts.append(sql.SQL("notes = {}").format(sql.Placeholder()))
            params.append(body.notes)
        if body.status == "accepted":
            set_parts.append(sql.SQL("accepted_at = NOW()"))
        elif body.status == "completed":
            set_parts.append(sql.SQL("completed_at = NOW()"))

        query = sql.SQL("UPDATE assignments SET {} WHERE id = {}").format(
            sql.SQL(", ").join(set_parts),
            sql.Placeholder(),
        )
        params.append(assignment_id)
        conn.execute(query, params)
        conn.commit()
        row = conn.execute(
            "SELECT * FROM assignments WHERE id = %s", (assignment_id,)
        ).fetchone()
        return AssignmentResponse.model_validate(dict(row))
    finally:
        conn.close()
