import json
import logging
from pathlib import Path

from app.config import DEMO_MODE

DATA_DIR = Path(__file__).parent.parent / "data"
SCENARIOS_DIR = DATA_DIR / "scenarios"

logger = logging.getLogger(__name__)


def get_weather_data() -> dict:
    """Return weather data based on current scenario step or default."""
    if DEMO_MODE:
        # Try scenario-based weather first
        try:
            from app.services.orchestration_engine import get_scenario
            scenario = get_scenario()
            scenario_file = SCENARIOS_DIR / f"{scenario}.json"
            if scenario_file.is_file():
                with open(scenario_file) as f:
                    return json.load(f)
        except Exception:
            pass  # Fall through to default

        # Default: sample_weather.json
        with open(DATA_DIR / "sample_weather.json") as f:
            return json.load(f)

    return {
        "source": "live",
        "note": "DEMO_MODE=false: integrate NOAA or your weather provider in weather_service.",
    }
