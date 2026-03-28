import json
from pathlib import Path

DATA_DIR = Path(__file__).parent.parent / "data"


def get_weather_data() -> dict:
    with open(DATA_DIR / "sample_weather.json") as f:
        return json.load(f)
