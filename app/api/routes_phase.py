from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.db.database import get_connection
from app.models.phase import PhaseResponse, PhaseSetRequest

router = APIRouter(tags=["phase"])

PHASES = ["pre_storm", "active_storm", "post_storm"]


class OrchestratorRequest(BaseModel):
    phase: Optional[str] = None


@router.get("/phase", response_model=PhaseResponse)
async def get_phase():
    conn = get_connection()
    try:
        row = conn.execute("SELECT * FROM phase WHERE id = 1").fetchone()
        return dict(row)
    finally:
        conn.close()


@router.post("/phase/advance", response_model=PhaseResponse)
async def advance_phase():
    conn = get_connection()
    try:
        row = conn.execute("SELECT * FROM phase WHERE id = 1").fetchone()
        current = row["current_phase"]
        idx = PHASES.index(current)
        if idx >= len(PHASES) - 1:
            raise HTTPException(status_code=400, detail="Already at final phase")
        next_phase = PHASES[idx + 1]
        conn.execute(
            "UPDATE phase SET current_phase = %s, updated_at = NOW() WHERE id = 1",
            (next_phase,),
        )
        conn.commit()
        row = conn.execute("SELECT * FROM phase WHERE id = 1").fetchone()
        return dict(row)
    finally:
        conn.close()


@router.post("/phase/set", response_model=PhaseResponse)
async def set_phase(request: PhaseSetRequest):
    if request.phase not in PHASES:
        raise HTTPException(
            status_code=400, detail=f"Invalid phase. Must be one of: {PHASES}"
        )
    conn = get_connection()
    try:
        conn.execute(
            "UPDATE phase SET current_phase = %s, updated_at = NOW() WHERE id = 1",
            (request.phase,),
        )
        conn.commit()
        row = conn.execute("SELECT * FROM phase WHERE id = 1").fetchone()
        return dict(row)
    finally:
        conn.close()


@router.post("/phase/orchestrate")
async def orchestrate(body: Optional[OrchestratorRequest] = None):
    """Run the full agent pipeline for the current (or specified) disaster phase.

    - Pre-storm: Monitor → Alert (sequential)
    - Active storm: Field Report → Severity → [Resource + Alert] (sequential + parallel)
    - Post-storm: [Reunification + Resource] (parallel)
    """
    from app.agents.orchestrator import run_orchestrator

    phase_override = body.phase if body else None
    result = await run_orchestrator(phase_override=phase_override)
    return result
