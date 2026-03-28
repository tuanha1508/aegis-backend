from __future__ import annotations

from typing import Any, Optional
from uuid import UUID, uuid4

import psycopg
from psycopg.types.json import Json


def insert_audit_log(
    conn: psycopg.Connection,
    agent_name: str,
    *,
    run_id: Optional[UUID] = None,
    phase: Optional[str] = None,
    input_payload: Optional[dict[str, Any]] = None,
    output_payload: Optional[dict[str, Any]] = None,
    error_message: Optional[str] = None,
    duration_ms: Optional[int] = None,
    related_report_id: Optional[int] = None,
    related_incident_id: Optional[int] = None,
    related_assignment_id: Optional[int] = None,
) -> dict[str, Any]:
    rid = run_id if run_id is not None else uuid4()
    row = conn.execute(
        """INSERT INTO audit_log (
            agent_name, run_id, phase, input_payload, output_payload,
            error_message, duration_ms, related_report_id, related_incident_id,
            related_assignment_id
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        RETURNING *""",
        (
            agent_name,
            rid,
            phase,
            Json(input_payload) if input_payload is not None else None,
            Json(output_payload) if output_payload is not None else None,
            error_message,
            duration_ms,
            related_report_id,
            related_incident_id,
            related_assignment_id,
        ),
    ).fetchone()
    return dict(row)
