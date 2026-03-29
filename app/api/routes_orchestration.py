"""Orchestration control endpoints — scenario management and auto-orchestration."""

from typing import Optional

from fastapi import APIRouter
from pydantic import BaseModel

from app.db.database import get_connection
from app.services.orchestration_engine import (
    collect_signals,
    evaluate_mode,
    set_scenario,
    get_scenario,
    start_scheduler,
    stop_scheduler,
    tick,
)

router = APIRouter(tags=["orchestration"])


class ScenarioRequest(BaseModel):
    step: str  # e.g. "storm_none", "storm_watch_72h", "storm_landfall"


@router.get("/orchestration/status")
async def orchestration_status():
    """Get current orchestration state, signals, and mode."""
    signals = collect_signals()
    mode = evaluate_mode(signals)
    return {
        "operational_mode": mode,
        "current_scenario": get_scenario(),
        "signals": signals,
    }


@router.post("/orchestration/scenario")
async def set_demo_scenario(body: ScenarioRequest):
    """Set the demo scenario step (changes weather data source).

    Available steps: storm_none, storm_watch_72h, storm_warning_24h,
    storm_imminent_6h, storm_landfall, storm_post_1d, storm_post_3d, storm_post_5d
    """
    set_scenario(body.step)
    return {"status": "ok", "scenario": body.step}


@router.post("/orchestration/tick")
async def manual_tick():
    """Manually trigger one orchestration tick.

    Evaluates signals, determines mode, runs due agent jobs.
    Use this during the demo instead of waiting for the background scheduler.
    """
    result = await tick()
    return result


@router.post("/orchestration/scheduler/start")
async def start_auto():
    """Start the background orchestration scheduler (ticks every 60s)."""
    start_scheduler()
    return {"status": "started"}


@router.post("/orchestration/scheduler/stop")
async def stop_auto():
    """Stop the background orchestration scheduler."""
    stop_scheduler()
    return {"status": "stopped"}
