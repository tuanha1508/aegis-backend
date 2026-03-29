"""
Orchestration Engine — Background scheduler that auto-runs agents based on signals.

Evaluates cheap signals (live weather, alerts, report backlog) every tick,
decides which agents to run, and manages phase transitions automatically.

Operational modes:
- idle: no storm, nothing runs
- storm_watch: storm approaching, monitor every 10 min
- active_storm: storm hitting, full pipeline running
- post_storm: recovery phase, daily runs for 5 days
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta, timezone
from typing import Any

from app.db.database import get_connection

logger = logging.getLogger(__name__)

TICK_INTERVAL_SECONDS = 60  # Check every minute
MONITOR_CADENCE_MINUTES = 10  # During storm watch/active
POST_STORM_DAYS = 5

# Background task handle
_scheduler_task: asyncio.Task | None = None


# ─── Signal Collection (cheap, no LLM) ──────────────────────

def collect_signals() -> dict[str, Any]:
    """Read cheap inputs to decide what agents should run."""
    conn = get_connection()
    try:
        phase = conn.execute("SELECT current_phase FROM phase WHERE id = 1").fetchone()
        current_phase = phase["current_phase"] if phase else "pre_storm"

        unprocessed = conn.execute(
            "SELECT COUNT(*) AS cnt FROM reports WHERE processed = FALSE"
        ).fetchone()["cnt"]

        unresolved = conn.execute(
            "SELECT COUNT(*) AS cnt FROM incidents WHERE resolved = FALSE"
        ).fetchone()["cnt"]

        orch = conn.execute(
            "SELECT * FROM orchestration_state WHERE id = 1"
        ).fetchone()

        risk_rows = conn.execute(
            "SELECT MAX(flood_risk) AS max_risk FROM risk_assessments"
        ).fetchone()
        max_risk = risk_rows["max_risk"] if risk_rows and risk_rows["max_risk"] else 0.0

        unmatched_found = conn.execute(
            "SELECT COUNT(*) AS cnt FROM found_persons WHERE matched_missing_id IS NULL"
        ).fetchone()["cnt"]

        missing_count = conn.execute(
            "SELECT COUNT(*) AS cnt FROM missing_persons WHERE status = 'missing'"
        ).fetchone()["cnt"]
    finally:
        conn.close()

    return {
        "current_phase": current_phase,
        "unprocessed_reports": unprocessed,
        "unresolved_incidents": unresolved,
        "max_flood_risk": max_risk,
        "unmatched_found": unmatched_found,
        "missing_count": missing_count,
        "orchestration_state": dict(orch) if orch else None,
    }


# ─── Mode Evaluation ─────────────────────────────────────────

def evaluate_mode(signals: dict) -> str:
    """Determine operational mode from signals.

    Uses the current phase + risk levels to decide mode.
    """
    phase = signals["current_phase"]
    max_risk = signals["max_flood_risk"]

    if phase == "active_storm":
        return "active_storm"
    if phase == "post_storm":
        return "post_storm"

    # pre_storm: check if there's actually a storm
    if max_risk >= 0.6:
        return "storm_watch"
    return "idle"


def evaluate_phase_transition(mode: str, signals: dict) -> str | None:
    """Decide if a phase transition is needed. Returns new phase or None."""
    current = signals["current_phase"]

    if mode == "active_storm" and current != "active_storm":
        return "active_storm"
    if mode == "post_storm" and current != "post_storm":
        return "post_storm"
    if mode in ("storm_watch", "idle") and current not in ("pre_storm",):
        # Don't auto-revert to pre_storm
        pass
    return None


# ─── Job Scheduling ──────────────────────────────────────────

def _minutes_since(ts: Any) -> float:
    """Minutes since a timestamp. Returns inf if ts is None."""
    if ts is None:
        return float("inf")
    if isinstance(ts, str):
        ts = datetime.fromisoformat(ts)
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)
    now = datetime.now(timezone.utc)
    return (now - ts).total_seconds() / 60


def determine_jobs(mode: str, signals: dict) -> list[str]:
    """Decide which agent jobs to run based on mode and cadence."""
    orch = signals.get("orchestration_state") or {}
    jobs = []

    if mode == "idle":
        return []

    if mode == "storm_watch":
        if _minutes_since(orch.get("last_monitor_run_at")) >= MONITOR_CADENCE_MINUTES:
            jobs.append("monitor")
            jobs.append("alerts")

    elif mode == "active_storm":
        if _minutes_since(orch.get("last_monitor_run_at")) >= MONITOR_CADENCE_MINUTES:
            jobs.append("monitor")

        if signals["unprocessed_reports"] > 0:
            jobs.append("field_report")

        if _minutes_since(orch.get("last_severity_run_at")) >= MONITOR_CADENCE_MINUTES:
            jobs.append("severity")

        if _minutes_since(orch.get("last_alert_run_at")) >= MONITOR_CADENCE_MINUTES:
            jobs.append("alerts")

    elif mode == "post_storm":
        # Check 5-day window
        post_start = orch.get("post_storm_started_at")
        if post_start and _minutes_since(post_start) > POST_STORM_DAYS * 24 * 60:
            # Past 5 days, only run if there's work
            if signals["unprocessed_reports"] == 0 and signals["unresolved_incidents"] == 0:
                return []

        # Daily cadence for post-storm
        if _minutes_since(orch.get("last_monitor_run_at")) >= 24 * 60:
            jobs.append("monitor")

        if signals["unprocessed_reports"] > 0:
            jobs.append("field_report")

        if signals["missing_count"] > 0 and signals["unmatched_found"] > 0:
            if _minutes_since(orch.get("last_reunification_run_at")) >= 60:
                jobs.append("reunification")

        if _minutes_since(orch.get("last_recovery_run_at")) >= 24 * 60:
            jobs.append("recovery")

    return jobs


# ─── Job Execution ────────────────────────────────────────────

async def run_jobs(jobs: list[str]) -> dict[str, str]:
    """Execute the given agent jobs and update orchestration state timestamps."""
    results = {}

    for job in jobs:
        try:
            if job == "monitor":
                from app.agents.monitor_agent import run_monitor_agent
                await run_monitor_agent()
                _update_timestamp("last_monitor_run_at")
                results[job] = "success"

            elif job == "alerts":
                from app.agents.alert_agent import run_alert_agent
                await run_alert_agent()
                _update_timestamp("last_alert_run_at")
                results[job] = "success"

            elif job == "field_report":
                from app.agents.field_report_agent import run_field_report_agent
                await run_field_report_agent()
                _update_timestamp("last_report_process_at")
                results[job] = "success"

            elif job == "severity":
                from app.agents.severity_agent import run_severity_agent
                await run_severity_agent()
                _update_timestamp("last_severity_run_at")
                results[job] = "success"

            elif job == "reunification":
                from app.agents.reunification_agent import run_reunification_agent
                await run_reunification_agent()
                _update_timestamp("last_reunification_run_at")
                results[job] = "success"

            elif job == "recovery":
                # Use the recovery endpoint logic
                _update_timestamp("last_recovery_run_at")
                results[job] = "skipped"  # Recovery agent runs via endpoint

        except Exception as e:
            logger.error("Job %s failed: %s", job, e)
            results[job] = f"error: {e}"

    return results


def _update_timestamp(field: str):
    """Update a timestamp in orchestration_state."""
    conn = get_connection()
    try:
        conn.execute(
            f"UPDATE orchestration_state SET {field} = NOW(), updated_at = NOW() WHERE id = 1"
        )
        conn.commit()
    finally:
        conn.close()


def _update_mode(mode: str):
    """Update operational mode in orchestration_state."""
    conn = get_connection()
    try:
        conn.execute(
            "UPDATE orchestration_state SET operational_mode = %s, updated_at = NOW() WHERE id = 1",
            (mode,),
        )
        conn.commit()
    finally:
        conn.close()


def _transition_phase(new_phase: str):
    """Auto-transition the disaster phase."""
    conn = get_connection()
    try:
        conn.execute(
            "UPDATE phase SET current_phase = %s, updated_at = NOW() WHERE id = 1",
            (new_phase,),
        )
        if new_phase == "post_storm":
            conn.execute(
                "UPDATE orchestration_state SET post_storm_started_at = NOW() WHERE id = 1"
            )
        conn.commit()
    finally:
        conn.close()
    logger.info("Auto-transitioned phase to: %s", new_phase)


# ─── Scenario Control ────────────────────────────────────────

def set_scenario(step: str):
    """Set the current scenario step for demo mode."""
    conn = get_connection()
    try:
        conn.execute(
            "UPDATE orchestration_state SET scenario_step = %s, updated_at = NOW() WHERE id = 1",
            (step,),
        )
        conn.commit()
    finally:
        conn.close()


def get_scenario() -> str:
    """Get the current scenario step."""
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT scenario_step FROM orchestration_state WHERE id = 1"
        ).fetchone()
        return row["scenario_step"] if row else "storm_none"
    finally:
        conn.close()


# ─── Scheduler Tick ───────────────────────────────────────────

async def tick():
    """One orchestration tick — evaluate signals and run due jobs."""
    signals = collect_signals()
    mode = evaluate_mode(signals)
    _update_mode(mode)

    # Check for phase transition
    new_phase = evaluate_phase_transition(mode, signals)
    if new_phase:
        _transition_phase(new_phase)

    # Determine and run due jobs
    jobs = determine_jobs(mode, signals)
    if jobs:
        logger.info("Orchestrator tick: mode=%s, running jobs=%s", mode, jobs)
        results = await run_jobs(jobs)
        logger.info("Orchestrator results: %s", results)
        return {"mode": mode, "jobs_run": results}

    return {"mode": mode, "jobs_run": {}}


async def _scheduler_loop():
    """Background loop that runs tick() every TICK_INTERVAL_SECONDS."""
    while True:
        try:
            await tick()
        except Exception as e:
            logger.error("Orchestration tick failed: %s", e)
        await asyncio.sleep(TICK_INTERVAL_SECONDS)


def start_scheduler():
    """Start the background orchestration scheduler."""
    global _scheduler_task
    if _scheduler_task is not None:
        return  # Already running

    loop = asyncio.get_event_loop()
    _scheduler_task = loop.create_task(_scheduler_loop())
    logger.info("Orchestration scheduler started (tick every %ds)", TICK_INTERVAL_SECONDS)


def stop_scheduler():
    """Stop the background orchestration scheduler."""
    global _scheduler_task
    if _scheduler_task:
        _scheduler_task.cancel()
        _scheduler_task = None
        logger.info("Orchestration scheduler stopped")
