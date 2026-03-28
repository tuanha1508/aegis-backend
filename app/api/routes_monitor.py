import json
import logging
from pathlib import Path

from fastapi import APIRouter, HTTPException

from app.db.database import get_connection

router = APIRouter(tags=["monitor"])
logger = logging.getLogger(__name__)

DATA_DIR = Path(__file__).parent.parent / "data"


@router.get("/monitor/risk")
async def get_risk():
    conn = get_connection()
    rows = conn.execute(
        "SELECT * FROM risk_assessments ORDER BY flood_risk DESC"
    ).fetchall()
    conn.close()
    return {"neighborhoods": [dict(r) for r in rows]}


@router.get("/monitor/weather")
async def get_weather():
    with open(DATA_DIR / "sample_weather.json") as f:
        return json.load(f)


@router.post("/monitor/analyze")
async def analyze_risk():
    """Trigger the Monitor Agent to analyze storm data and produce risk assessments."""
    try:
        from app.agents.monitor_agent import run_monitor_agent

        result = await run_monitor_agent()
        return result
    except Exception as exc:
        logger.exception("Monitor Agent failed")
        raise HTTPException(status_code=500, detail=str(exc))
