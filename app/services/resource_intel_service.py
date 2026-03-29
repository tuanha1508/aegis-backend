"""
Apply crowdsourced resource status from field reports (incident_type=resource_status).

Only updates the database when name+location matching is confident; logs to audit_log.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

import psycopg

from app.db.audit import insert_audit_log
from app.db.database import get_connection
from app.services.geo_match import haversine_m, names_match

logger = logging.getLogger(__name__)

MAX_MATCH_RADIUS_M = 15_000.0
NOTES_MAX_LEN = 500

# Types to search when keywords are ambiguous
_DEFAULT_TYPES = ("shelter", "supply_point", "medical")


def _infer_status_from_text(text: str) -> str | None:
    t = text.lower()
    if any(x in t for x in ("closed", "shut", "not accepting", "shut down")):
        return "closed"
    if any(x in t for x in ("full", "at capacity", "no room", "turned away", "completely full")):
        return "full"
    if any(
        x in t
        for x in (
            "limited",
            "running low",
            "low on",
            "out of food",
            "out of water",
            "no food",
            "no water",
            "ran out",
        )
    ):
        return "limited"
    return None


def _infer_resource_types(haystack: str) -> tuple[str, ...]:
    t = haystack.lower()
    out: list[str] = []
    if any(
        k in t
        for k in (
            "shelter",
            "church",
            "convention center",
            "high school",
            "marshall",
            "baptist",
        )
    ):
        out.append("shelter")
    if any(
        k in t
        for k in (
            "food bank",
            "feeding",
            "distribution",
            "supply",
            "metropolitan ministries",
            "groceries",
        )
    ):
        out.append("supply_point")
    if "hospital" in t or "medical" in t or "clinic" in t:
        out.append("medical")
    return tuple(dict.fromkeys(out)) if out else _DEFAULT_TYPES


def _append_note(prev: str | None, line: str) -> str:
    base = (prev or "").strip()
    new = f"{base}\n{line}".strip() if base else line
    if len(new) > NOTES_MAX_LEN:
        new = new[-NOTES_MAX_LEN:]
    return new


def _pick_matching_resource(
    conn: psycopg.Connection,
    report: dict[str, Any],
) -> dict[str, Any] | None:
    haystack = f"{report.get('raw_text') or ''} {report.get('location_text') or ''}"
    types = _infer_resource_types(haystack)
    placeholders = ",".join(["%s"] * len(types))
    rows = conn.execute(
        f"SELECT * FROM resources WHERE type IN ({placeholders})",
        types,
    ).fetchall()
    if not rows:
        return None

    matched: list[tuple[float, dict[str, Any]]] = []
    for r in rows:
        if not names_match(str(r["name"]), haystack):
            continue
        lat, lng = report.get("lat"), report.get("lng")
        if lat is not None and lng is not None:
            d = haversine_m(float(lat), float(lng), float(r["lat"]), float(r["lng"]))
        else:
            d = 0.0
        matched.append((d, dict(r)))

    if not matched:
        return None

    if report.get("lat") is not None and report.get("lng") is not None:
        matched = [(d, r) for d, r in matched if d <= MAX_MATCH_RADIUS_M]

    if len(matched) == 1:
        return matched[0][1]

    if len(matched) > 1:
        if report.get("lat") is None:
            return None
        matched.sort(key=lambda x: x[0])
        if matched[0][0] < matched[1][0]:
            return matched[0][1]
        return None

    return None


def _process_one_report(conn: psycopg.Connection, report: dict[str, Any]) -> str:
    rid = report["id"]
    raw = report.get("raw_text") or ""
    status = _infer_status_from_text(raw)
    if not status:
        conn.execute(
            "UPDATE reports SET resource_intel_applied = TRUE WHERE id = %s",
            (rid,),
        )
        insert_audit_log(
            conn,
            agent_name="resource_intel",
            run_id=uuid4(),
            phase=None,
            input_payload={"report_id": rid, "reason": "no_status_keywords"},
            output_payload={"skipped": True},
            related_report_id=rid,
        )
        return "skipped_no_keywords"

    resource = _pick_matching_resource(conn, report)
    if not resource:
        conn.execute(
            "UPDATE reports SET resource_intel_applied = TRUE WHERE id = %s",
            (rid,),
        )
        insert_audit_log(
            conn,
            agent_name="resource_intel",
            run_id=uuid4(),
            phase=None,
            input_payload={"report_id": rid, "reason": "no_confident_resource_match"},
            output_payload={"skipped": True},
            related_report_id=rid,
        )
        return "skipped_no_match"

    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%MZ")
    line = f"intel report#{rid} {ts}: status={status}"
    new_notes = _append_note(resource.get("notes"), line)

    conn.execute(
        """
        UPDATE resources
        SET status = %s, notes = %s, last_updated = NOW()
        WHERE id = %s
        """,
        (status, new_notes, resource["id"]),
    )
    conn.execute(
        "UPDATE reports SET resource_intel_applied = TRUE WHERE id = %s",
        (rid,),
    )
    insert_audit_log(
        conn,
        agent_name="resource_intel",
        run_id=uuid4(),
        phase=None,
        input_payload={"report_id": rid, "resource_id": resource["id"]},
        output_payload={"status": status, "resource_name": resource.get("name")},
        related_report_id=rid,
    )
    return "applied"


async def run_resource_intel(conn: psycopg.Connection | None = None) -> dict[str, Any]:
    """Process pending resource_status reports; commit when owning connection."""
    own_conn = conn is None
    if own_conn:
        conn = get_connection()
    assert conn is not None

    applied = 0
    skipped = 0
    errors: list[str] = []
    rows: list[Any] = []

    try:
        rows = list(
            conn.execute(
                """
                SELECT * FROM reports
                WHERE processed = TRUE
                  AND incident_type = 'resource_status'
                  AND COALESCE(resource_intel_applied, FALSE) = FALSE
                ORDER BY created_at ASC
                """
            ).fetchall()
        )

        for row in rows:
            try:
                result = _process_one_report(conn, dict(row))
                if result == "applied":
                    applied += 1
                else:
                    skipped += 1
            except Exception as ex:
                logger.exception("resource_intel failed for report %s", row.get("id"))
                errors.append(f"report {row.get('id')}: {ex}")

        if own_conn:
            conn.commit()
    except Exception:
        if own_conn:
            conn.rollback()
        raise
    finally:
        if own_conn:
            conn.close()

    return {
        "applied": applied,
        "skipped": skipped,
        "errors": errors,
        "pending_seen": len(rows),
    }
