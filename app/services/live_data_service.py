"""
Live Data Service — Fetches real-time data from free government APIs.

Sources:
- USGS Water Services (river gauge levels)
- NOAA CO-OPS (tide levels)
- NWS API (weather, alerts, forecast)
- NWS/USGS/NHC RSS feeds (news aggregation)
- YouTube live stream URLs (hardcoded)
"""

from __future__ import annotations

import asyncio
import logging
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta
from typing import Any

import httpx

logger = logging.getLogger(__name__)

NWS_HEADERS = {"User-Agent": "Aegis-StormIntel (hackusf2026@example.com)"}

# ─── USGS Real-Time Water Levels ─────────────────────────────

# Corrected USGS stations with accurate flood stages
# 02306028: Downtown Tampa tidal gauge — flood stage from NWS AHPS
# 02301500: Alafia River — reliable inland gauge
# 02300500: Little Manatee River — southern Hillsborough County
# 02304500: Hillsborough River upstream — flood stage = 32 ft per NWS
USGS_STATIONS = {
    "02306028": {"name": "Hillsborough River at Platt St, Tampa", "flood_stage_ft": 14.0},
    "02301500": {"name": "Alafia River at Lithia", "flood_stage_ft": 15.0},
    "02300500": {"name": "Little Manatee River near Wimauma", "flood_stage_ft": 11.0},
    "02304500": {"name": "Hillsborough River near Tampa", "flood_stage_ft": 32.0},
}


async def get_water_levels() -> dict:
    """Fetch water levels — simulated during demo, real from USGS otherwise."""
    try:
        from app.services.orchestration_engine import get_scenario
        scenario = get_scenario()
        if scenario != "storm_none" and scenario in _DEMO_WATER:
            from datetime import datetime
            now = datetime.utcnow().isoformat()
            stations = []
            for s in _DEMO_WATER[scenario]:
                stations.append({
                    **s,
                    "station_id": "SIM",
                    "lat": 27.95, "lng": -82.46,
                    "change_1h": 0.5 if s["trend"] == "rising" else -0.3,
                    "readings_24h": [],
                    "last_updated": now,
                })
            return {"stations": stations, "fetched_at": now}
    except Exception:
        pass
    site_ids = ",".join(USGS_STATIONS.keys())
    url = (
        f"https://waterservices.usgs.gov/nwis/iv/"
        f"?sites={site_ids}&parameterCd=00065&period=P1D&format=json"
    )
    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.get(url)
        resp.raise_for_status()
        data = resp.json()

    stations = []
    for ts in data.get("value", {}).get("timeSeries", []):
        source = ts.get("sourceInfo", {})
        site_code = source.get("siteCode", [{}])[0].get("value", "")
        geo = source.get("geoLocation", {}).get("geogLocation", {})
        meta = USGS_STATIONS.get(site_code, {})

        readings = ts.get("values", [{}])[0].get("value", [])
        if not readings:
            continue

        values = [{"time": r["dateTime"], "value": float(r["value"])} for r in readings]
        current = values[-1]["value"]

        # Trend: compare to ~1 hour ago
        hour_ago_idx = max(0, len(values) - 5)  # ~15min intervals, 4 readings ≈ 1hr
        change_1h = round(current - values[hour_ago_idx]["value"], 2)
        if change_1h > 0.1:
            trend = "rising"
        elif change_1h < -0.1:
            trend = "falling"
        else:
            trend = "stable"

        flood_stage = meta.get("flood_stage_ft", 10.0)
        pct = round(current / flood_stage * 100, 1) if flood_stage > 0 else 0.0
        stations.append({
            "station_id": site_code,
            "name": meta.get("name", source.get("siteName", "")),
            "lat": geo.get("latitude"),
            "lng": geo.get("longitude"),
            "current_level_ft": current,
            "trend": trend,
            "change_1h": change_1h,
            "readings_24h": values,
            "flood_stage_ft": flood_stage,
            "percent_of_flood": pct,
            "last_updated": readings[-1]["dateTime"],
        })

    return {"stations": stations, "fetched_at": datetime.utcnow().isoformat()}


# ─── NOAA Tides & Currents ───────────────────────────────────

async def get_tide_data() -> dict:
    """Fetch tide observations and predictions from NOAA CO-OPS API."""
    today = datetime.utcnow().strftime("%Y%m%d")
    tomorrow = (datetime.utcnow() + timedelta(days=1)).strftime("%Y%m%d")

    base = "https://api.tidesandcurrents.noaa.gov/api/prod/datagetter"
    params_obs = {
        "station": "8726520", "product": "water_level", "datum": "MLLW",
        "units": "english", "time_zone": "lst_ldt", "format": "json",
        "date": "latest", "range": "24", "application": "aegis",
    }
    params_pred = {
        "station": "8726520", "product": "predictions", "datum": "MLLW",
        "units": "english", "time_zone": "lst_ldt", "format": "json",
        "begin_date": today, "end_date": tomorrow, "interval": "hilo",
        "application": "aegis",
    }

    async with httpx.AsyncClient(timeout=15) as client:
        obs_resp, pred_resp = await asyncio_gather(
            client.get(base, params=params_obs),
            client.get(base, params=params_pred),
        )

    obs_data = obs_resp.json().get("data", [])
    pred_data = pred_resp.json().get("predictions", [])

    observations = []
    current_level = None
    for r in obs_data:
        try:
            observations.append({"time": r["t"], "level_ft": float(r["v"])})
        except (KeyError, ValueError):
            continue
    if observations:
        current_level = observations[-1]["level_ft"]

    predictions = []
    next_high = None
    next_low = None
    now_str = datetime.utcnow().strftime("%Y-%m-%d %H:%M")
    for p in pred_data:
        try:
            entry = {
                "time": p["t"],
                "level_ft": float(p["v"]),
                "type": "high" if p.get("type") == "H" else "low",
            }
        except (KeyError, ValueError):
            continue
        predictions.append(entry)
        if p["t"] > now_str:
            if p.get("type") == "H" and not next_high:
                next_high = entry
            elif p.get("type") == "L" and not next_low:
                next_low = entry

    return {
        "station": "St. Petersburg, FL",
        "current_level_ft": current_level,
        "datum": "MLLW",
        "observations_24h": observations,
        "next_high_tide": next_high,
        "next_low_tide": next_low,
        "tide_predictions": predictions,
        "fetched_at": datetime.utcnow().isoformat(),
    }


async def asyncio_gather(*coros):
    """Helper to gather async coroutines."""
    return await asyncio.gather(*coros)


# ─── NWS Current Weather Observation ─────────────────────────

def _degrees_to_cardinal(deg: float | None) -> str:
    if deg is None:
        return "N/A"
    dirs = ["N", "NNE", "NE", "ENE", "E", "ESE", "SE", "SSE",
            "S", "SSW", "SW", "WSW", "W", "WNW", "NW", "NNW"]
    return dirs[int((deg + 11.25) / 22.5) % 16]


_DEMO_WEATHER: dict[str, dict] = {
    "storm_watch_72h": {"station": "Tampa Intl (SIM)", "temperature_f": 84.0, "wind_speed_mph": 15.0, "wind_gust_mph": 22.0, "wind_direction": "SE", "wind_direction_degrees": 135, "barometric_pressure_inhg": 29.85, "humidity_percent": 82.0, "conditions": "Partly Cloudy, Tropical Disturbance"},
    "storm_warning_24h": {"station": "Tampa Intl (SIM)", "temperature_f": 82.0, "wind_speed_mph": 35.0, "wind_gust_mph": 48.0, "wind_direction": "ESE", "wind_direction_degrees": 112, "barometric_pressure_inhg": 29.45, "humidity_percent": 88.0, "conditions": "Rain, Tropical Storm Force Winds"},
    "storm_imminent_6h": {"station": "Tampa Intl (SIM)", "temperature_f": 79.0, "wind_speed_mph": 65.0, "wind_gust_mph": 85.0, "wind_direction": "E", "wind_direction_degrees": 90, "barometric_pressure_inhg": 28.90, "humidity_percent": 95.0, "conditions": "Heavy Rain, Hurricane Warning"},
    "storm_landfall": {"station": "Tampa Intl (SIM)", "temperature_f": 76.0, "wind_speed_mph": 95.0, "wind_gust_mph": 120.0, "wind_direction": "NE", "wind_direction_degrees": 45, "barometric_pressure_inhg": 28.15, "humidity_percent": 98.0, "conditions": "Extreme — Hurricane Landfall, 120mph Winds"},
    "storm_post_1d": {"station": "Tampa Intl (SIM)", "temperature_f": 78.0, "wind_speed_mph": 25.0, "wind_gust_mph": 35.0, "wind_direction": "NW", "wind_direction_degrees": 315, "barometric_pressure_inhg": 29.50, "humidity_percent": 85.0, "conditions": "Cloudy, Diminishing Winds"},
    "storm_post_3d": {"station": "Tampa Intl (SIM)", "temperature_f": 80.0, "wind_speed_mph": 12.0, "wind_gust_mph": None, "wind_direction": "W", "wind_direction_degrees": 270, "barometric_pressure_inhg": 30.00, "humidity_percent": 75.0, "conditions": "Partly Cloudy, Recovery Ops"},
    "storm_post_5d": {"station": "Tampa Intl (SIM)", "temperature_f": 82.0, "wind_speed_mph": 8.0, "wind_gust_mph": None, "wind_direction": "SW", "wind_direction_degrees": 225, "barometric_pressure_inhg": 30.10, "humidity_percent": 70.0, "conditions": "Clear"},
}

_DEMO_WATER: dict[str, list[dict]] = {
    "storm_watch_72h": [
        {"name": "Hillsborough River at Platt St", "current_level_ft": 10.2, "flood_stage_ft": 14.0, "trend": "rising", "percent_of_flood": 72.9},
        {"name": "Alafia River at Lithia", "current_level_ft": 4.5, "flood_stage_ft": 15.0, "trend": "rising", "percent_of_flood": 30.0},
        {"name": "Little Manatee River", "current_level_ft": 5.2, "flood_stage_ft": 11.0, "trend": "rising", "percent_of_flood": 47.3},
        {"name": "Hillsborough River near Tampa", "current_level_ft": 24.0, "flood_stage_ft": 32.0, "trend": "rising", "percent_of_flood": 75.0},
    ],
    "storm_warning_24h": [
        {"name": "Hillsborough River at Platt St", "current_level_ft": 11.8, "flood_stage_ft": 14.0, "trend": "rising", "percent_of_flood": 84.3},
        {"name": "Alafia River at Lithia", "current_level_ft": 8.2, "flood_stage_ft": 15.0, "trend": "rising", "percent_of_flood": 54.7},
        {"name": "Little Manatee River", "current_level_ft": 7.8, "flood_stage_ft": 11.0, "trend": "rising", "percent_of_flood": 70.9},
        {"name": "Hillsborough River near Tampa", "current_level_ft": 27.5, "flood_stage_ft": 32.0, "trend": "rising", "percent_of_flood": 85.9},
    ],
    "storm_imminent_6h": [
        {"name": "Hillsborough River at Platt St", "current_level_ft": 13.5, "flood_stage_ft": 14.0, "trend": "rising", "percent_of_flood": 96.4},
        {"name": "Alafia River at Lithia", "current_level_ft": 12.1, "flood_stage_ft": 15.0, "trend": "rising", "percent_of_flood": 80.7},
        {"name": "Little Manatee River", "current_level_ft": 9.8, "flood_stage_ft": 11.0, "trend": "rising", "percent_of_flood": 89.1},
        {"name": "Hillsborough River near Tampa", "current_level_ft": 30.5, "flood_stage_ft": 32.0, "trend": "rising", "percent_of_flood": 95.3},
    ],
    "storm_landfall": [
        {"name": "Hillsborough River at Platt St", "current_level_ft": 16.8, "flood_stage_ft": 14.0, "trend": "rising", "percent_of_flood": 120.0},
        {"name": "Alafia River at Lithia", "current_level_ft": 17.3, "flood_stage_ft": 15.0, "trend": "rising", "percent_of_flood": 115.3},
        {"name": "Little Manatee River", "current_level_ft": 13.5, "flood_stage_ft": 11.0, "trend": "rising", "percent_of_flood": 122.7},
        {"name": "Hillsborough River near Tampa", "current_level_ft": 35.2, "flood_stage_ft": 32.0, "trend": "rising", "percent_of_flood": 110.0},
    ],
    "storm_post_1d": [
        {"name": "Hillsborough River at Platt St", "current_level_ft": 14.5, "flood_stage_ft": 14.0, "trend": "falling", "percent_of_flood": 103.6},
        {"name": "Alafia River at Lithia", "current_level_ft": 13.8, "flood_stage_ft": 15.0, "trend": "falling", "percent_of_flood": 92.0},
        {"name": "Little Manatee River", "current_level_ft": 10.2, "flood_stage_ft": 11.0, "trend": "falling", "percent_of_flood": 92.7},
        {"name": "Hillsborough River near Tampa", "current_level_ft": 31.0, "flood_stage_ft": 32.0, "trend": "falling", "percent_of_flood": 96.9},
    ],
    "storm_post_3d": [
        {"name": "Hillsborough River at Platt St", "current_level_ft": 11.5, "flood_stage_ft": 14.0, "trend": "falling", "percent_of_flood": 82.1},
        {"name": "Alafia River at Lithia", "current_level_ft": 7.5, "flood_stage_ft": 15.0, "trend": "falling", "percent_of_flood": 50.0},
        {"name": "Little Manatee River", "current_level_ft": 6.2, "flood_stage_ft": 11.0, "trend": "falling", "percent_of_flood": 56.4},
        {"name": "Hillsborough River near Tampa", "current_level_ft": 26.0, "flood_stage_ft": 32.0, "trend": "falling", "percent_of_flood": 81.3},
    ],
}


async def get_current_weather() -> dict:
    """Fetch weather — simulated during demo, real from NWS otherwise."""
    try:
        from app.services.orchestration_engine import get_scenario
        scenario = get_scenario()
        if scenario != "storm_none" and scenario in _DEMO_WEATHER:
            from datetime import datetime
            w = _DEMO_WEATHER[scenario].copy()
            w["observed_at"] = datetime.utcnow().isoformat()
            w["fetched_at"] = datetime.utcnow().isoformat()
            return w
    except Exception:
        pass

    url = "https://api.weather.gov/stations/KTPA/observations/latest"
    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.get(url, headers=NWS_HEADERS)
        resp.raise_for_status()
        data = resp.json()["properties"]

    def safe_val(field: dict | None) -> float | None:
        return field.get("value") if field else None

    temp_c = safe_val(data.get("temperature"))
    wind_kmh = safe_val(data.get("windSpeed"))
    gust_kmh = safe_val(data.get("windGust"))
    wind_deg = safe_val(data.get("windDirection"))
    pressure_pa = safe_val(data.get("barometricPressure"))
    humidity = safe_val(data.get("relativeHumidity"))

    return {
        "station": "Tampa International Airport",
        "temperature_f": round(temp_c * 9 / 5 + 32, 1) if temp_c is not None else None,
        "wind_speed_mph": round(wind_kmh * 0.621371, 1) if wind_kmh is not None else None,
        "wind_gust_mph": round(gust_kmh * 0.621371, 1) if gust_kmh is not None else None,
        "wind_direction": _degrees_to_cardinal(wind_deg),
        "wind_direction_degrees": wind_deg,
        "barometric_pressure_inhg": round(pressure_pa / 3386.39, 2) if pressure_pa else None,
        "humidity_percent": round(humidity, 1) if humidity is not None else None,
        "conditions": data.get("textDescription", ""),
        "observed_at": data.get("timestamp", ""),
        "fetched_at": datetime.utcnow().isoformat(),
    }


# ─── NWS Active Alerts ───────────────────────────────────────

async def get_active_alerts() -> dict:
    """Fetch active weather alerts for Hillsborough County."""
    url = "https://api.weather.gov/alerts/active?zone=FLC057"
    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.get(url, headers=NWS_HEADERS)
        resp.raise_for_status()
        data = resp.json()

    alerts = []
    for feat in data.get("features", []):
        p = feat.get("properties", {})
        alerts.append({
            "event": p.get("event", ""),
            "headline": p.get("headline", ""),
            "description": p.get("description", ""),
            "severity": p.get("severity", "Unknown"),
            "urgency": p.get("urgency", "Unknown"),
            "onset": p.get("onset", ""),
            "expires": p.get("expires", ""),
            "sender": p.get("senderName", ""),
            "areas": p.get("areaDesc", ""),
        })

    return {
        "zone": "Hillsborough County, FL",
        "active_count": len(alerts),
        "alerts": alerts,
        "fetched_at": datetime.utcnow().isoformat(),
    }


# ─── NWS Forecast ────────────────────────────────────────────

async def get_forecast() -> dict:
    """Fetch 7-day forecast for Tampa from NWS (two-step lookup)."""
    async with httpx.AsyncClient(timeout=15) as client:
        # Step 1: get forecast URL
        points_resp = await client.get(
            "https://api.weather.gov/points/27.9506,-82.4572",
            headers=NWS_HEADERS,
        )
        points_resp.raise_for_status()
        forecast_url = points_resp.json()["properties"]["forecast"]

        # Step 2: get forecast
        fc_resp = await client.get(forecast_url, headers=NWS_HEADERS)
        fc_resp.raise_for_status()
        periods_raw = fc_resp.json()["properties"]["periods"]

    periods = []
    for p in periods_raw:
        periods.append({
            "name": p["name"],
            "temperature_f": p["temperature"],
            "wind_speed": p["windSpeed"],
            "wind_direction": p["windDirection"],
            "short_forecast": p["shortForecast"],
            "detailed_forecast": p["detailedForecast"],
            "is_daytime": p["isDaytime"],
        })

    return {
        "location": "Tampa, FL",
        "periods": periods,
        "fetched_at": datetime.utcnow().isoformat(),
    }


# ─── News Aggregation ────────────────────────────────────────

def _categorize(text: str) -> str:
    t = text.lower()
    if "hurricane" in t or "tropical" in t:
        return "hurricane"
    if "flood" in t or "water level" in t or "surge" in t:
        return "flood"
    if "tornado" in t:
        return "tornado"
    if "thunder" in t or "lightning" in t:
        return "thunderstorm"
    return "other"


# Simulated storm news for demo mode — realistic Hurricane Milton headlines
_DEMO_NEWS: dict[str, list[dict]] = {
    "storm_watch_72h": [
        {"source": "NHC", "title": "Tropical Storm Milton forms in Gulf of Mexico", "summary": "A tropical storm has formed in the southwestern Gulf of Mexico and is expected to intensify rapidly over the next 48 hours.", "severity": "moderate", "category": "hurricane"},
        {"source": "NWS Tampa Bay", "title": "Tampa Bay under Tropical Storm Watch", "summary": "A Tropical Storm Watch has been issued for the Tampa Bay area as Milton tracks northeast.", "severity": "severe", "category": "hurricane"},
        {"source": "FOX 13 Tampa", "title": "Tampa residents urged to prepare emergency supplies", "summary": "Officials urge Tampa Bay residents to stock up on water, batteries, and non-perishable food as Milton approaches.", "severity": "moderate", "category": "other"},
    ],
    "storm_warning_24h": [
        {"source": "NHC", "title": "BREAKING: Milton rapidly intensifies to Category 5", "summary": "Hurricane Milton has explosively intensified to Category 5 with maximum sustained winds of 180 mph, making it one of the strongest Atlantic hurricanes on record.", "severity": "extreme", "category": "hurricane"},
        {"source": "NWS Tampa Bay", "title": "Hurricane Warning issued for Hillsborough County", "summary": "A Hurricane Warning is now in effect for the Tampa Bay metro area. Life-threatening storm surge of 10-15 feet expected.", "severity": "extreme", "category": "hurricane"},
        {"source": "FEMA", "title": "FEMA pre-positions resources ahead of Milton landfall", "summary": "FEMA has pre-positioned disaster response teams and supplies across Florida ahead of Hurricane Milton's expected landfall.", "severity": "severe", "category": "hurricane"},
        {"source": "FOX 13 Tampa", "title": "Mandatory evacuation ordered for Zone A in Hillsborough County", "summary": "Hillsborough County has issued mandatory evacuation orders for Zone A residents. Shelters are now open.", "severity": "extreme", "category": "hurricane"},
    ],
    "storm_imminent_6h": [
        {"source": "NHC", "title": "Milton weakens to Category 3 but expands — landfall in 6 hours", "summary": "Hurricane Milton has weakened slightly to Category 3 with 120 mph winds but its wind field has nearly doubled in size.", "severity": "extreme", "category": "hurricane"},
        {"source": "NWS Tampa Bay", "title": "URGENT: Storm surge warning — 10-15 feet possible in Tampa Bay", "summary": "A catastrophic storm surge of 10-15 feet above normal tide levels is possible along the Tampa Bay coastline.", "severity": "extreme", "category": "flood"},
        {"source": "WTSP Tampa", "title": "I-275 gridlocked as Tampa evacuees flee north", "summary": "Major evacuation routes including I-275 and I-75 are experiencing severe congestion as residents flee ahead of Milton.", "severity": "severe", "category": "other"},
        {"source": "FOX 13 Tampa", "title": "Tampa International Airport closed ahead of Milton", "summary": "Tampa International Airport has suspended all operations and closed to the public ahead of Hurricane Milton.", "severity": "severe", "category": "hurricane"},
        {"source": "NWS Tampa Bay", "title": "Flash Flood Warning for Hillsborough and Pinellas counties", "summary": "A Flash Flood Warning is in effect. Rainfall rates of 3-5 inches per hour expected during Milton's passage.", "severity": "extreme", "category": "flood"},
    ],
    "storm_landfall": [
        {"source": "NHC", "title": "BREAKING: Hurricane Milton makes landfall near Siesta Key as Category 3", "summary": "Hurricane Milton has made landfall near Siesta Key, FL with maximum sustained winds of 120 mph at 8:30 PM EDT.", "severity": "extreme", "category": "hurricane"},
        {"source": "NWS Tampa Bay", "title": "EXTREME DANGER: Storm surge flooding ongoing in Tampa Bay", "summary": "Life-threatening storm surge flooding is occurring across Tampa Bay. Water levels 6-8 feet above normal.", "severity": "extreme", "category": "flood"},
        {"source": "WTSP Tampa", "title": "Multiple water rescues underway in South Tampa", "summary": "Tampa Fire Rescue reports multiple water rescues in progress in South Tampa, Davis Islands, and Palma Ceia neighborhoods.", "severity": "extreme", "category": "flood"},
        {"source": "FOX 13 Tampa", "title": "Widespread power outages across Tampa Bay — 1.5 million without power", "summary": "Over 1.5 million customers are without power across the Tampa Bay region as Milton's winds tear through the area.", "severity": "severe", "category": "hurricane"},
        {"source": "USGS", "title": "Hillsborough River at record levels — major flooding", "summary": "USGS gauges show the Hillsborough River at Tampa has reached record flood stage levels.", "severity": "extreme", "category": "flood"},
        {"source": "NWS Tampa Bay", "title": "Tornado Warning for eastern Hillsborough County", "summary": "A confirmed tornado has been spotted near Brandon. Take shelter immediately in an interior room.", "severity": "extreme", "category": "tornado"},
    ],
    "storm_post_1d": [
        {"source": "NHC", "title": "Milton exits Florida — tropical storm force winds diminishing", "summary": "Hurricane Milton has crossed the Florida peninsula and moved into the Atlantic. Tropical storm warnings are being discontinued.", "severity": "moderate", "category": "hurricane"},
        {"source": "FEMA", "title": "FEMA activates Major Disaster Declaration for Florida", "summary": "President has declared a Major Disaster for Florida counties affected by Hurricane Milton, unlocking federal assistance.", "severity": "severe", "category": "hurricane"},
        {"source": "FOX 13 Tampa", "title": "Milton aftermath: Assessing damage across Tampa Bay", "summary": "As daylight reveals the extent of Milton's destruction, rescue teams are conducting door-to-door searches in flooded neighborhoods.", "severity": "severe", "category": "hurricane"},
        {"source": "WTSP Tampa", "title": "Boil water advisory issued for Tampa and surrounding areas", "summary": "City of Tampa has issued a boil water advisory after Milton damaged water treatment infrastructure.", "severity": "moderate", "category": "other"},
    ],
    "storm_post_3d": [
        {"source": "FEMA", "title": "FEMA disaster recovery centers opening across Tampa Bay", "summary": "FEMA is opening disaster recovery centers in Hillsborough, Pinellas, and Manatee counties for Milton survivors.", "severity": "moderate", "category": "hurricane"},
        {"source": "FOX 13 Tampa", "title": "Power restoration progressing — 500,000 still without electricity", "summary": "Utility crews from across the nation are working to restore power. Approximately 500,000 customers remain without service.", "severity": "moderate", "category": "other"},
        {"source": "NWS Tampa Bay", "title": "River flooding slowly receding across Tampa Bay area", "summary": "Flood waters are gradually receding but several neighborhoods remain underwater. Residents urged to avoid flood water.", "severity": "moderate", "category": "flood"},
    ],
    "storm_post_5d": [
        {"source": "FEMA", "title": "Over $500M in federal aid approved for Milton recovery", "summary": "FEMA has approved over $500 million in federal disaster assistance for individuals and communities affected by Milton.", "severity": "minor", "category": "hurricane"},
        {"source": "FOX 13 Tampa", "title": "Tampa Bay begins long road to recovery after Milton", "summary": "Community organizations and volunteers are mobilizing to help Tampa Bay residents rebuild after Hurricane Milton.", "severity": "minor", "category": "other"},
    ],
}


async def get_news_feed() -> dict:
    """Aggregate storm/weather news. In demo mode, return simulated headlines."""
    # Check if we're in a demo scenario
    try:
        from app.services.orchestration_engine import get_scenario
        scenario = get_scenario()
    except Exception:
        scenario = "storm_none"

    # If in a demo scenario, return simulated storm news
    if scenario != "storm_none" and scenario in _DEMO_NEWS:
        from datetime import datetime, timedelta
        now = datetime.utcnow()
        demo_items = []
        for i, item in enumerate(_DEMO_NEWS[scenario]):
            demo_items.append({
                **item,
                "url": "",
                "published_at": (now - timedelta(minutes=i * 5)).isoformat() + "Z",
            })
        return {
            "items": demo_items,
            "source_count": len({i["source"] for i in demo_items}),
            "total_items": len(demo_items),
            "fetched_at": now.isoformat() + "Z",
        }
    items: list[dict] = []

    async with httpx.AsyncClient(timeout=15) as client:
        # 1. NHC Atlantic RSS
        try:
            resp = await client.get("https://www.nhc.noaa.gov/index-at.xml")
            if resp.status_code == 200:
                root = ET.fromstring(resp.text)
                for item in root.findall(".//item"):
                    title = item.findtext("title", "")
                    items.append({
                        "source": "NHC",
                        "title": title,
                        "summary": item.findtext("description", "")[:300],
                        "url": item.findtext("link", ""),
                        "published_at": item.findtext("pubDate", ""),
                        "severity": "severe" if "warning" in title.lower() else "moderate",
                        "category": _categorize(title),
                    })
        except (httpx.HTTPError, ET.ParseError) as e:
            logger.warning("NHC RSS fetch failed: %s", e)

        # 2. NWS Tampa Bay Atom feed
        try:
            resp = await client.get(
                "https://alerts.weather.gov/cap/wwaatmget.php?x=FLC057&y=1"
            )
            if resp.status_code == 200:
                ns = {"atom": "http://www.w3.org/2005/Atom"}
                root = ET.fromstring(resp.text)
                for entry in root.findall("atom:entry", ns):
                    title = entry.findtext("atom:title", "", ns)
                    items.append({
                        "source": "NWS Tampa Bay",
                        "title": title,
                        "summary": entry.findtext("atom:summary", "", ns)[:300],
                        "url": entry.find("atom:link", ns).get("href", "") if entry.find("atom:link", ns) is not None else "",
                        "published_at": entry.findtext("atom:updated", "", ns),
                        "severity": "severe",
                        "category": _categorize(title),
                    })
        except (httpx.HTTPError, ET.ParseError) as e:
            logger.warning("NWS Atom feed failed: %s", e)

        # 3. FEMA recent FL declarations (deduplicate by disaster number)
        try:
            resp = await client.get(
                "https://www.fema.gov/api/open/v2/DisasterDeclarationsSummaries",
                params={"$filter": "state eq 'FL'", "$orderby": "declarationDate desc", "$top": "20"},
            )
            if resp.status_code == 200:
                seen_disasters: set[str] = set()
                for dec in resp.json().get("DisasterDeclarationsSummaries", []):
                    disaster_num = str(dec.get("disasterNumber", ""))
                    if disaster_num in seen_disasters:
                        continue
                    seen_disasters.add(disaster_num)
                    title_name = dec.get("declarationTitle", "")
                    items.append({
                        "source": "FEMA",
                        "title": f"FEMA: {title_name}",
                        "summary": f"{dec.get('incidentType', '')} — declared {dec.get('declarationDate', '')[:10]} — {dec.get('designatedArea', '')}",
                        "url": f"https://www.fema.gov/disaster/{disaster_num}",
                        "published_at": dec.get("declarationDate", ""),
                        "severity": "severe" if "hurricane" in title_name.lower() else "moderate",
                        "category": _categorize(title_name),
                    })
                    if len(seen_disasters) >= 5:
                        break
        except (httpx.HTTPError, KeyError, ValueError) as e:
            logger.warning("FEMA API fetch failed: %s", e)

        # 4. FOX 13 Tampa Bay RSS (always has content)
        try:
            resp = await client.get("https://www.fox13news.com/rss/category/news")
            if resp.status_code == 200:
                root = ET.fromstring(resp.text)
                for item in root.findall(".//item")[:8]:
                    title = item.findtext("title", "")
                    items.append({
                        "source": "FOX 13 Tampa",
                        "title": title,
                        "summary": (item.findtext("description", "") or "")[:300],
                        "url": item.findtext("link", ""),
                        "published_at": item.findtext("pubDate", ""),
                        "severity": "moderate",
                        "category": _categorize(title),
                    })
        except (httpx.HTTPError, ET.ParseError) as e:
            logger.warning("FOX 13 RSS fetch failed: %s", e)

        # 5. WTSP 10 Tampa Bay RSS (always has content)
        try:
            resp = await client.get("https://www.wtsp.com/feeds/syndication/rss/news")
            if resp.status_code == 200:
                root = ET.fromstring(resp.text)
                for item in root.findall(".//item")[:8]:
                    title = item.findtext("title", "")
                    items.append({
                        "source": "WTSP Tampa",
                        "title": title,
                        "summary": (item.findtext("description", "") or "")[:300],
                        "url": item.findtext("link", ""),
                        "published_at": item.findtext("pubDate", ""),
                        "severity": "minor",
                        "category": _categorize(title),
                    })
        except (httpx.HTTPError, ET.ParseError) as e:
            logger.warning("WTSP RSS fetch failed: %s", e)

        # 6. NWS Florida-wide active alerts (always has something)
        try:
            resp = await client.get(
                "https://api.weather.gov/alerts/active?area=FL",
                headers=NWS_HEADERS,
            )
            if resp.status_code == 200:
                for feat in resp.json().get("features", [])[:5]:
                    p = feat.get("properties", {})
                    headline = p.get("headline", "")
                    items.append({
                        "source": "NWS Florida",
                        "title": p.get("event", "Weather Alert"),
                        "summary": headline[:300],
                        "url": p.get("@id", ""),
                        "published_at": p.get("onset", ""),
                        "severity": p.get("severity", "moderate").lower(),
                        "category": _categorize(p.get("event", "")),
                    })
        except (httpx.HTTPError, KeyError) as e:
            logger.warning("NWS FL alerts fetch failed: %s", e)

        # 7. NWS Tampa Bay forecast discussion (latest)
        try:
            resp = await client.get(
                "https://api.weather.gov/products/types/AFD/locations/TBW",
                headers=NWS_HEADERS,
            )
            if resp.status_code == 200:
                products = resp.json().get("@graph", [])[:1]
                for prod in products:
                    prod_url = prod.get("@id", "")
                    if prod_url:
                        detail = await client.get(prod_url, headers=NWS_HEADERS)
                        if detail.status_code == 200:
                            text = detail.json().get("productText", "")
                            items.append({
                                "source": "NWS Forecast",
                                "title": "Tampa Bay Area Forecast Discussion",
                                "summary": text[:300].replace("\n", " "),
                                "url": prod_url,
                                "published_at": prod.get("issuanceTime", ""),
                                "severity": "minor",
                                "category": "other",
                            })
        except (httpx.HTTPError, KeyError) as e:
            logger.warning("NWS AFD fetch failed: %s", e)

    # Deduplicate by title and filter out generic filler
    seen_titles: set[str] = set()
    deduped: list[dict] = []
    for item in items:
        title = item["title"].strip().lower()
        # Skip generic NHC filler
        if "hurricane season runs from" in title:
            continue
        if title not in seen_titles:
            seen_titles.add(title)
            deduped.append(item)
    items = deduped

    # Sort newest first, limit 20
    items.sort(key=lambda x: x.get("published_at", ""), reverse=True)
    items = items[:20]

    return {
        "items": items,
        "source_count": len({i["source"] for i in items}),
        "total_items": len(items),
        "fetched_at": datetime.utcnow().isoformat(),
    }


# ─── Live Stream URLs ────────────────────────────────────────

def get_live_streams() -> dict:
    """Return YouTube URLs for Tampa Bay hurricane coverage.

    Includes both channel pages (for live streams when active) and
    archived Hurricane Milton 2024 coverage as fallback content.
    """
    return {
        "streams": [
            # Live channel links (work when stations are broadcasting)
            {
                "name": "FOX 13 Tampa Bay",
                "description": "FOX affiliate — Tampa Bay weather and storm tracking",
                "youtube_channel_url": "https://www.youtube.com/@FOX13TampaBay",
                "live_url": "https://www.youtube.com/watch?v=pqaareyk7W8",
                "embed_url": "https://www.youtube.com/embed/pqaareyk7W8",
                "is_local": True,
            },
            {
                "name": "WTSP Tampa Bay — Milton Landfall",
                "description": "Hurricane Milton coverage, Oct 9 2024 (4 hours)",
                "youtube_channel_url": "https://www.youtube.com/@10TampaBay",
                "live_url": "https://www.youtube.com/watch?v=N21HO6WV6WI",
                "embed_url": "https://www.youtube.com/embed/N21HO6WV6WI",
                "is_local": True,
            },
            {
                "name": "Reuters — Milton Landfall Live",
                "description": "Hurricane Milton makes landfall in Tampa, Florida",
                "youtube_channel_url": "https://www.youtube.com/@reuters",
                "live_url": "https://www.youtube.com/watch?v=2k6OMI7uvhI",
                "embed_url": "https://www.youtube.com/embed/2k6OMI7uvhI",
                "is_local": False,
            },
        ]
    }
