import logging

from fastapi import APIRouter, HTTPException

from app.db.database import get_connection
from app.services.weather_service import get_weather_data

router = APIRouter(tags=["monitor"])
logger = logging.getLogger(__name__)


@router.get("/monitor/risk")
async def get_risk():
    conn = get_connection()
    try:
        rows = conn.execute(
            "SELECT * FROM risk_assessments ORDER BY flood_risk DESC NULLS LAST"
        ).fetchall()
        return {"neighborhoods": [dict(r) for r in rows]}
    finally:
        conn.close()


@router.get("/monitor/weather")
async def get_weather():
    return get_weather_data()


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
