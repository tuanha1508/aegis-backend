from fastapi import APIRouter, HTTPException
from app.db.database import get_connection
from app.models.phase import PhaseResponse, PhaseSetRequest

router = APIRouter(tags=["phase"])

PHASES = ["pre_storm", "active_storm", "post_storm"]


@router.get("/phase", response_model=PhaseResponse)
async def get_phase():
    conn = get_connection()
    row = conn.execute("SELECT * FROM phase WHERE id = 1").fetchone()
    conn.close()
    return dict(row)


@router.post("/phase/advance", response_model=PhaseResponse)
async def advance_phase():
    conn = get_connection()
    row = conn.execute("SELECT * FROM phase WHERE id = 1").fetchone()
    current = row["current_phase"]
    idx = PHASES.index(current)
    if idx >= len(PHASES) - 1:
        conn.close()
        raise HTTPException(status_code=400, detail="Already at final phase")
    next_phase = PHASES[idx + 1]
    conn.execute(
        "UPDATE phase SET current_phase = ?, updated_at = CURRENT_TIMESTAMP WHERE id = 1",
        (next_phase,),
    )
    conn.commit()
    row = conn.execute("SELECT * FROM phase WHERE id = 1").fetchone()
    conn.close()
    return dict(row)


@router.post("/phase/set", response_model=PhaseResponse)
async def set_phase(request: PhaseSetRequest):
    if request.phase not in PHASES:
        raise HTTPException(
            status_code=400, detail=f"Invalid phase. Must be one of: {PHASES}"
        )
    conn = get_connection()
    conn.execute(
        "UPDATE phase SET current_phase = ?, updated_at = CURRENT_TIMESTAMP WHERE id = 1",
        (request.phase,),
    )
    conn.commit()
    row = conn.execute("SELECT * FROM phase WHERE id = 1").fetchone()
    conn.close()
    return dict(row)
