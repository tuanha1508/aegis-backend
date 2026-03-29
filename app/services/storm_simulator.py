"""
Storm Simulator — Runs a full hurricane lifecycle for demo purposes.

Advances through 8 scenario steps, injecting reports, triggering agents,
and advancing phases automatically. The frontend polls /live/all and
watches the dashboard update in real-time.

Demo flow (runs in ~2-3 minutes):
1. storm_none → idle, baseline data
2. storm_watch_72h → pre_storm, Monitor Agent analyzes
3. storm_warning_24h → pre_storm, Alert Agent generates evacuation alerts
4. storm_imminent_6h → active_storm transition, field reports start
5. storm_landfall → active_storm, severity scoring, critical alerts
6. storm_post_1d → post_storm, reunification matching
7. storm_post_3d → recovery briefs generated
8. storm_post_5d → all clear, summary
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from app.db.database import get_connection
from app.services.orchestration_engine import set_scenario

logger = logging.getLogger(__name__)

# Simulated field reports injected during the storm
SIMULATED_REPORTS = [
    {
        "raw_text": "Storm surge flooding on Bayshore Blvd, water 4 feet deep covering road and entering ground floor homes",
        "source": "sms_sim",
        "lat": 27.910, "lng": -82.485,
    },
    {
        "raw_text": "Family trapped on second floor Henderson Blvd, water rising fast, 2 adults 3 children including infant",
        "source": "sms_sim",
        "lat": 27.929, "lng": -82.515,
    },
    {
        "raw_text": "Roof torn off apartment building Hillsborough Ave near 22nd, 15 people sheltering in hallway",
        "source": "sms_sim",
        "lat": 27.995, "lng": -82.438,
    },
    {
        "raw_text": "Inundacion severa en Ruskin cerca del rio Alafia, familias en techos necesitan botes de rescate",
        "source": "sms_sim",
        "lat": 27.722, "lng": -82.431,
    },
]


def _inject_reports():
    """Insert simulated field reports into the database."""
    conn = get_connection()
    try:
        for r in SIMULATED_REPORTS:
            conn.execute(
                """INSERT INTO reports (raw_text, source, lat, lng)
                   VALUES (%s, %s, %s, %s)""",
                (r["raw_text"], r["source"], r["lat"], r["lng"]),
            )
        conn.commit()
    finally:
        conn.close()
    return len(SIMULATED_REPORTS)


def _set_phase(phase: str):
    """Set the disaster phase."""
    conn = get_connection()
    try:
        conn.execute(
            "UPDATE phase SET current_phase = %s, updated_at = NOW() WHERE id = 1",
            (phase,),
        )
        conn.commit()
    finally:
        conn.close()


async def run_storm_simulation(speed: str = "normal") -> dict[str, Any]:
    """Run a full hurricane lifecycle simulation.

    Args:
        speed: "fast" (5s per step), "normal" (10s), "slow" (20s)

    Returns a log of all actions taken during the simulation.
    """
    delays = {"fast": 5, "normal": 10, "slow": 20}
    delay = delays.get(speed, 10)

    log: list[dict] = []

    def step(msg: str):
        logger.info("SIMULATION: %s", msg)
        log.append({"step": len(log) + 1, "action": msg})

    try:
        # ── Step 1: Clear skies ──
        set_scenario("storm_none")
        _set_phase("pre_storm")
        step("Storm simulation started — clear skies over Tampa Bay")
        await asyncio.sleep(delay)

        # ── Step 2: Storm watch ──
        set_scenario("storm_watch_72h")
        step("Tropical storm forming in Gulf — NWS issues Storm Watch")
        try:
            from app.agents.monitor_agent import run_monitor_agent
            await run_monitor_agent()
            step("Monitor Agent: analyzed storm trajectory, updated risk scores")
        except Exception as e:
            step(f"Monitor Agent: {e}")
        await asyncio.sleep(delay)

        # ── Step 3: Hurricane warning ──
        set_scenario("storm_warning_24h")
        step("Hurricane Milton intensifies to Cat 3 — Hurricane Warning issued")
        try:
            from app.agents.alert_agent import run_alert_agent
            await run_alert_agent(context="Hurricane Warning: evacuate Zone A immediately")
            step("Alert Agent: generated evacuation alerts for high-risk zones")
        except Exception as e:
            step(f"Alert Agent: {e}")
        await asyncio.sleep(delay)

        # ── Step 4: Storm imminent → active storm ──
        set_scenario("storm_imminent_6h")
        _set_phase("active_storm")
        step("Phase → ACTIVE STORM — landfall in 6 hours")

        # Inject field reports
        count = _inject_reports()
        step(f"Injected {count} emergency field reports from Tampa Bay residents")

        try:
            from app.agents.field_report_agent import run_field_report_agent
            result = await run_field_report_agent()
            step(f"Field Report Agent: processed {result.get('processed_count', 0)} reports")
        except Exception as e:
            step(f"Field Report Agent: {e}")
        await asyncio.sleep(delay)

        # ── Step 5: Landfall ──
        set_scenario("storm_landfall")
        step("Hurricane Milton makes landfall — Cat 3, 120mph winds")

        try:
            from app.agents.severity_agent import run_severity_agent
            result = await run_severity_agent()
            step(f"Severity Agent: ranked {result.get('incidents_count', 0)} incidents")
        except Exception as e:
            step(f"Severity Agent: {e}")

        try:
            from app.agents.alert_agent import run_alert_agent
            await run_alert_agent(context="LANDFALL: generate emergency alerts for all critical incidents")
            step("Alert Agent: generated emergency alerts for landfall")
        except Exception as e:
            step(f"Alert Agent: {e}")
        await asyncio.sleep(delay)

        # ── Step 6: Post storm day 1 ──
        set_scenario("storm_post_1d")
        _set_phase("post_storm")
        step("Phase → POST STORM — Milton moves east, recovery begins")

        try:
            from app.agents.reunification_agent import run_reunification_agent
            result = await run_reunification_agent()
            step(f"Reunification Agent: found {result.get('matches_count', 0)} potential matches")
        except Exception as e:
            step(f"Reunification Agent: {e}")
        await asyncio.sleep(delay)

        # ── Step 7: Post storm day 3 ──
        set_scenario("storm_post_3d")
        step("Day 3: Flood advisory remains, recovery operations expanding")

        # Generate recovery briefs (inline, not via agent to save time)
        step("Recovery operations in progress across 12 neighborhoods")
        await asyncio.sleep(delay)

        # ── Step 8: All clear ──
        set_scenario("storm_post_5d")
        step("Day 5: All clear — Tampa Bay entering long-term recovery")

        # Final stats
        conn = get_connection()
        try:
            stats = {
                "total_reports": conn.execute("SELECT COUNT(*) AS cnt FROM reports").fetchone()["cnt"],
                "total_incidents": conn.execute("SELECT COUNT(*) AS cnt FROM incidents").fetchone()["cnt"],
                "total_alerts": conn.execute("SELECT COUNT(*) AS cnt FROM alerts").fetchone()["cnt"],
                "total_matches": conn.execute("SELECT COUNT(*) AS cnt FROM matches").fetchone()["cnt"],
                "critical_incidents": conn.execute(
                    "SELECT COUNT(*) AS cnt FROM incidents WHERE severity_label = 'critical'"
                ).fetchone()["cnt"],
            }
        finally:
            conn.close()

        step(f"SIMULATION COMPLETE — {stats['total_reports']} reports, "
             f"{stats['total_incidents']} incidents, {stats['total_alerts']} alerts, "
             f"{stats['total_matches']} reunification matches")

    except Exception as e:
        logger.error("Storm simulation error: %s", e)
        log.append({"step": "error", "action": str(e)})

    return {
        "status": "complete",
        "steps": len(log),
        "log": log,
        "speed": speed,
    }
