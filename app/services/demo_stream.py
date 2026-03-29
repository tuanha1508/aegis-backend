"""Demo Stream — Simulates real-time data flowing into Aegis.

Injects found persons and resource occupancy updates every 3-5 seconds
so the frontend dashboard visibly refreshes during the hackathon demo.
No LLM calls — data is inserted directly for reliability and speed.
"""

from __future__ import annotations

import asyncio
import logging
import random
from typing import Any

from app.db.database import get_connection

logger = logging.getLogger(__name__)

# ── Simulated found-person check-ins ──────────────────────────

STREAM_FOUND_PERSONS: list[dict[str, Any]] = [
    {
        "name": "Elena Rodriguez",
        "age_approx": 45,
        "gender": "female",
        "description": "Hispanic woman, dark hair, wearing hospital scrubs, minor arm injury",
        "found_at": "USF Marshall Center",
        "found_lat": 28.0587,
        "found_lng": -82.4137,
    },
    {
        "name": "James W.",
        "age_approx": 55,
        "gender": "male",
        "description": "African-American man, gray beard, limping, carrying two trash bags of belongings",
        "found_at": "Middleton High School",
        "found_lat": 27.9876,
        "found_lng": -82.4367,
    },
    {
        "name": "Maria G.",
        "age_approx": 70,
        "gender": "female",
        "description": "Elderly Hispanic woman with walker, blue floral dress, disoriented, Spanish speaking",
        "found_at": "Sickles High School",
        "found_lat": 28.0745,
        "found_lng": -82.5805,
    },
    {
        "name": "Tommy A.",
        "age_approx": 8,
        "gender": "male",
        "description": "Young boy, brown hair, red Spider-Man backpack, came with Wilson family",
        "found_at": "Steinbrenner High School",
        "found_lat": 28.1447,
        "found_lng": -82.5125,
    },
    {
        "name": "Patricia Chen",
        "age_approx": 62,
        "gender": "female",
        "description": "Asian woman, short black hair, wearing raincoat, carrying cat in carrier",
        "found_at": "Pizzo Elementary School",
        "found_lat": 28.0632,
        "found_lng": -82.4089,
    },
    {
        "name": "Robert M.",
        "age_approx": 64,
        "gender": "male",
        "description": "Bald man, hard of hearing, diabetic, arrived wet and cold, asked for insulin",
        "found_at": "Shields Middle School",
        "found_lat": 27.7216,
        "found_lng": -82.4312,
    },
    {
        "name": "David Williams",
        "age_approx": 34,
        "gender": "male",
        "description": "Tall, wearing Tampa Bay Buccaneers jersey, carrying toddler",
        "found_at": "Burnett Middle School",
        "found_lat": 27.9943,
        "found_lng": -82.2812,
    },
    {
        "name": "Sarah Nguyen",
        "age_approx": 28,
        "gender": "female",
        "description": "Pregnant, approximately 7 months, wearing University of Tampa sweatshirt",
        "found_at": "Erwin Technical College (Special Needs)",
        "found_lat": 27.9952,
        "found_lng": -82.4383,
    },
]

# ── Simulated resource occupancy changes ──────────────────────
# Each entry fuzzy-matches an existing seeded resource by name.

STREAM_RESOURCE_UPDATES: list[dict[str, Any]] = [
    {"match_name": "Middleton High School", "current_occupancy": 280, "status": "open"},
    {"match_name": "Sickles High School", "current_occupancy": 310, "status": "open"},
    {"match_name": "Steinbrenner High School", "current_occupancy": 200, "status": "open"},
    {"match_name": "Middleton High School", "current_occupancy": 420, "status": "limited"},
    {"match_name": "Shields Middle School", "current_occupancy": 250, "status": "limited"},
    {"match_name": "Sickles High School", "current_occupancy": 480, "status": "limited"},
    {"match_name": "Middleton High School", "current_occupancy": 500, "status": "full"},
    {"match_name": "Pizzo Elementary School", "current_occupancy": 180, "status": "limited"},
]

# ── Interleaved schedule: (type, pool_index) ─────────────────
# Alternates between found persons and resource updates for a
# realistic mixed feed.

_SCHEDULE: list[tuple[str, int]] = []
_fi, _ri = 0, 0
for _i in range(len(STREAM_FOUND_PERSONS) + len(STREAM_RESOURCE_UPDATES)):
    if _fi < len(STREAM_FOUND_PERSONS) and (_ri >= len(STREAM_RESOURCE_UPDATES) or _i % 2 == 0):
        _SCHEDULE.append(("person", _fi))
        _fi += 1
    elif _ri < len(STREAM_RESOURCE_UPDATES):
        _SCHEDULE.append(("resource", _ri))
        _ri += 1


# ── Stream state ──────────────────────────────────────────────

class _StreamState:
    running: bool = False
    task: asyncio.Task | None = None
    injected: int = 0
    total: int = len(_SCHEDULE)


_state = _StreamState()


def _inject_found_person(data: dict[str, Any]) -> None:
    conn = get_connection()
    try:
        conn.execute(
            """INSERT INTO found_persons
               (name, age_approx, gender, description, found_at, found_lat, found_lng)
               VALUES (%s, %s, %s, %s, %s, %s, %s)""",
            (
                data["name"],
                data.get("age_approx"),
                data.get("gender"),
                data.get("description", ""),
                data.get("found_at", ""),
                data.get("found_lat"),
                data.get("found_lng"),
            ),
        )
        conn.commit()
    finally:
        conn.close()


def _inject_resource_update(data: dict[str, Any]) -> None:
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT id FROM resources WHERE LOWER(name) = LOWER(%s)",
            (data["match_name"],),
        ).fetchone()
        if row:
            conn.execute(
                "UPDATE resources SET current_occupancy = %s, status = %s, last_updated = NOW() WHERE id = %s",
                (data["current_occupancy"], data["status"], row["id"]),
            )
        conn.commit()
    finally:
        conn.close()


async def _stream_loop() -> None:
    """Background coroutine that walks through the schedule."""
    try:
        for kind, idx in _SCHEDULE:
            if not _state.running:
                break
            if kind == "person":
                _inject_found_person(STREAM_FOUND_PERSONS[idx])
                logger.info("Demo stream: injected found person %s", STREAM_FOUND_PERSONS[idx]["name"])
            else:
                _inject_resource_update(STREAM_RESOURCE_UPDATES[idx])
                logger.info("Demo stream: updated resource %s", STREAM_RESOURCE_UPDATES[idx]["match_name"])
            _state.injected += 1
            await asyncio.sleep(random.uniform(3.0, 5.0))
    except asyncio.CancelledError:
        pass
    except Exception:
        logger.exception("Demo stream error")
    finally:
        _state.running = False


async def start_stream() -> dict[str, Any]:
    """Start the demo data stream.  Returns immediately."""
    if _state.running:
        return {"status": "already_running", "injected": _state.injected, "total": _state.total}

    _state.running = True
    _state.injected = 0
    _state.task = asyncio.create_task(_stream_loop())

    return {"status": "started", "total": _state.total}


def stop_stream() -> dict[str, Any]:
    """Cancel the demo stream."""
    _state.running = False
    if _state.task and not _state.task.done():
        _state.task.cancel()
    return {"status": "stopped", "injected": _state.injected, "total": _state.total}


def stream_status() -> dict[str, Any]:
    return {
        "running": _state.running,
        "injected": _state.injected,
        "total": _state.total,
    }
