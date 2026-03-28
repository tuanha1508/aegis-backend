import json
from pathlib import Path
from fastapi import APIRouter
from app.db.database import get_connection

router = APIRouter(tags=["monitor"])

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
