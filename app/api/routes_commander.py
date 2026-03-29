"""Commander + Storm Simulation endpoints."""

from typing import Optional

from fastapi import APIRouter
from pydantic import BaseModel

router = APIRouter(tags=["commander"])


class CommanderRequest(BaseModel):
    question: str


class SimulationRequest(BaseModel):
    speed: Optional[str] = "normal"  # "fast", "normal", "slow"


@router.post("/commander/ask")
async def ask_commander(body: CommanderRequest):
    """Ask the Situation Commander any question about the disaster.

    The Commander queries all specialist agents and returns a
    synthesized, authoritative answer.

    Examples:
    - "What's the current situation?"
    - "Is Davis Islands safe?"
    - "Has Maria Garcia been found?"
    - "Where can people shelter?"
    - "What should we do next?"
    """
    from app.agents.commander_agent import run_commander

    result = await run_commander(body.question)
    return result


@router.post("/simulation/start")
async def start_simulation(body: Optional[SimulationRequest] = None):
    """Start a full hurricane lifecycle simulation.

    Runs through 8 storm phases automatically, triggering agents
    at each step. The frontend polls /live/all to watch the
    dashboard update in real-time.

    Speed options:
    - "fast": 5s per step (~40s total)
    - "normal": 10s per step (~80s total)
    - "slow": 20s per step (~160s total)
    """
    from app.services.storm_simulator import run_storm_simulation

    speed = body.speed if body else "normal"
    result = await run_storm_simulation(speed=speed)
    return result


@router.get("/simulation/status")
async def simulation_status():
    """Get current simulation/scenario state."""
    from app.services.orchestration_engine import get_scenario
    from app.db.database import get_connection

    conn = get_connection()
    try:
        phase = conn.execute("SELECT current_phase FROM phase WHERE id = 1").fetchone()
        stats = {
            "reports": conn.execute("SELECT COUNT(*) AS cnt FROM reports").fetchone()["cnt"],
            "incidents": conn.execute("SELECT COUNT(*) AS cnt FROM incidents").fetchone()["cnt"],
            "alerts": conn.execute("SELECT COUNT(*) AS cnt FROM alerts").fetchone()["cnt"],
            "matches": conn.execute("SELECT COUNT(*) AS cnt FROM matches").fetchone()["cnt"],
        }
    finally:
        conn.close()

    return {
        "phase": phase["current_phase"] if phase else "unknown",
        "scenario": get_scenario(),
        "stats": stats,
    }
