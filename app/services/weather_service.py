import json
from pathlib import Path

from app.config import DEMO_MODE

DATA_DIR = Path(__file__).parent.parent / "data"


def get_weather_data() -> dict:
    if DEMO_MODE:
        with open(DATA_DIR / "sample_weather.json") as f:
            return json.load(f)
    return {
        "source": "live",
        "note": "DEMO_MODE=false: integrate NOAA or your weather provider in weather_service.",
    }
