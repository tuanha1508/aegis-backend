"""
Agent Pipeline — Auto-cascading agent chains triggered by events.

When a report comes in, this pipeline automatically:
1. Field Report Agent parses it
2. Severity Agent scores it (if enough unprocessed reports)
3. Alert Agent fires if any incident is critical

This is the "autonomous workforce" — agents react to events
without human button-clicking.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from app.db.database import get_connection

logger = logging.getLogger(__name__)

# Thresholds
SEVERITY_AUTO_THRESHOLD = 75  # Auto-generate alert if incident score >= this
BATCH_SEVERITY_THRESHOLD = 3  # Run severity after this many unprocessed-but-parsed reports


async def auto_cascade_report(report_id: int) -> dict[str, Any]:
    """Run the automatic pipeline after a report is processed.

    Called after Field Report Agent parses a single report.
    Checks if severity scoring + alerting should auto-trigger.

    Returns a dict describing what actions were taken.
    """
    actions: list[str] = []

    # Check how many parsed-but-not-incident reports exist
    conn = get_connection()
    try:
        # Count processed reports
        processed = conn.execute(
            "SELECT COUNT(*) AS cnt FROM reports WHERE processed = TRUE"
        ).fetchone()["cnt"]

        # Count existing incidents
        incident_count = conn.execute(
            "SELECT COUNT(*) AS cnt FROM incidents"
        ).fetchone()["cnt"]

        # Get the report we just processed
        report = conn.execute(
            "SELECT * FROM reports WHERE id = %s", (report_id,)
        ).fetchone()
    finally:
        conn.close()

    if not report:
        return {"actions": [], "reason": "report not found"}

    # Auto-severity: run if we have enough parsed reports without incidents,
    # OR if this report mentions trapped/medical (urgent)
    urgent_types = {"trapped_person", "medical_emergency", "structural_damage", "fire"}
    is_urgent = report.get("incident_type") in urgent_types

    if is_urgent or processed >= BATCH_SEVERITY_THRESHOLD:
        try:
            from app.agents.severity_agent import run_severity_agent
            severity_result = await run_severity_agent()
            actions.append(f"severity_agent: {severity_result.get('incidents_count', 0)} incidents")

            # Check if any new critical incidents → auto-alert
            conn = get_connection()
            try:
                critical = conn.execute(
                    """SELECT COUNT(*) AS cnt FROM incidents
                       WHERE severity_score >= %s AND resolved = FALSE""",
                    (SEVERITY_AUTO_THRESHOLD,),
                ).fetchone()["cnt"]
            finally:
                conn.close()

            if critical > 0:
                from app.agents.alert_agent import run_alert_agent
                alert_result = await run_alert_agent(
                    context=f"Auto-triggered: {critical} critical incidents detected"
                )
                actions.append(f"alert_agent: {alert_result.get('alerts_generated', 0)} alerts")

        except Exception as e:
            logger.error("Auto-cascade severity/alert failed: %s", e)
            actions.append(f"error: {e}")

    return {
        "actions": actions,
        "is_urgent": is_urgent,
        "processed_count": processed,
    }


async def auto_cascade_phase_change(new_phase: str) -> dict[str, Any]:
    """Run agents automatically when the phase changes.

    - pre_storm → run Monitor + Alert
    - active_storm → run Field Report (batch) + Severity + Alert
    - post_storm → run Reunification + Recovery
    """
    actions: list[str] = []

    try:
        if new_phase == "pre_storm":
            from app.agents.monitor_agent import run_monitor_agent
            from app.agents.alert_agent import run_alert_agent

            await run_monitor_agent()
            actions.append("monitor_agent")
            await run_alert_agent()
            actions.append("alert_agent")

        elif new_phase == "active_storm":
            from app.agents.field_report_agent import run_field_report_agent
            from app.agents.severity_agent import run_severity_agent
            from app.agents.alert_agent import run_alert_agent

            await run_field_report_agent()
            actions.append("field_report_agent")
            await run_severity_agent()
            actions.append("severity_agent")
            await run_alert_agent(context="Phase changed to active storm")
            actions.append("alert_agent")

        elif new_phase == "post_storm":
            from app.agents.reunification_agent import run_reunification_agent

            await run_reunification_agent()
            actions.append("reunification_agent")

    except Exception as e:
        logger.error("Auto-cascade phase change failed: %s", e)
        actions.append(f"error: {e}")

    return {"phase": new_phase, "actions": actions}
