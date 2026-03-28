from fastapi import APIRouter
from app.db.database import get_connection
from app.services.weather_service import get_weather_data

router = APIRouter(tags=["monitor"])


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
