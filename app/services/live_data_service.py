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

import xml.etree.ElementTree as ET
from datetime import datetime, timedelta
from typing import Any

import httpx

NWS_HEADERS = {"User-Agent": "Aegis-StormIntel (hackusf2026@example.com)"}

# ─── USGS Real-Time Water Levels ─────────────────────────────

USGS_STATIONS = {
    "02304500": {"name": "Hillsborough River at Tampa", "flood_stage_ft": 12.0},
    "02301500": {"name": "Alafia River at Lithia", "flood_stage_ft": 15.0},
    "02300500": {"name": "Little Manatee River near Wimauma", "flood_stage_ft": 11.0},
    "02301990": {"name": "Palm River near Tampa", "flood_stage_ft": 8.0},
}


async def get_water_levels() -> dict:
    """Fetch real-time water levels from USGS Water Services API."""
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
            "percent_of_flood": round(current / flood_stage * 100, 1),
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

    observations = [{"time": r["t"], "level_ft": float(r["v"])} for r in obs_data]
    current_level = float(obs_data[-1]["v"]) if obs_data else None

    predictions = []
    next_high = None
    next_low = None
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M")
    for p in pred_data:
        entry = {
            "time": p["t"],
            "level_ft": float(p["v"]),
            "type": "high" if p.get("type") == "H" else "low",
        }
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
    import asyncio
    return await asyncio.gather(*coros)


# ─── NWS Current Weather Observation ─────────────────────────

def _degrees_to_cardinal(deg: float | None) -> str:
    if deg is None:
        return "N/A"
    dirs = ["N", "NNE", "NE", "ENE", "E", "ESE", "SE", "SSE",
            "S", "SSW", "SW", "WSW", "W", "WNW", "NW", "NNW"]
    return dirs[int((deg + 11.25) / 22.5) % 16]


async def get_current_weather() -> dict:
    """Fetch latest weather observation from NWS for Tampa International Airport."""
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


async def get_news_feed() -> dict:
    """Aggregate storm/weather news from NWS, USGS, NHC, and FEMA."""
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
        except Exception:
            pass

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
        except Exception:
            pass

        # 3. FEMA recent FL declarations
        try:
            resp = await client.get(
                "https://www.fema.gov/api/open/v2/DisasterDeclarationsSummaries",
                params={"$filter": "state eq 'FL'", "$orderby": "declarationDate desc", "$top": "5"},
            )
            if resp.status_code == 200:
                for dec in resp.json().get("DisasterDeclarationsSummaries", []):
                    title = f"FEMA Disaster: {dec.get('declarationTitle', '')}"
                    items.append({
                        "source": "FEMA",
                        "title": title,
                        "summary": f"{dec.get('incidentType', '')} — {dec.get('designatedArea', '')}",
                        "url": f"https://www.fema.gov/disaster/{dec.get('disasterNumber', '')}",
                        "published_at": dec.get("declarationDate", ""),
                        "severity": "moderate",
                        "category": _categorize(title),
                    })
        except Exception:
            pass

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
    """Return hardcoded YouTube live stream URLs for Tampa Bay news stations."""
    return {
        "streams": [
            {
                "name": "Bay News 9",
                "description": "Spectrum Bay News 9 — Tampa Bay's 24/7 local news",
                "youtube_channel_url": "https://www.youtube.com/@BayNews9",
                "live_url": "https://www.youtube.com/@BayNews9/live",
                "embed_url": None,
                "is_local": True,
            },
            {
                "name": "WFLA News Channel 8",
                "description": "NBC affiliate — Tampa Bay storm coverage",
                "youtube_channel_url": "https://www.youtube.com/@WFLANewsChannel8",
                "live_url": "https://www.youtube.com/@WFLANewsChannel8/live",
                "embed_url": None,
                "is_local": True,
            },
            {
                "name": "FOX 13 Tampa Bay",
                "description": "FOX affiliate — Tampa Bay weather and storm tracking",
                "youtube_channel_url": "https://www.youtube.com/@FOX13TampaBay",
                "live_url": "https://www.youtube.com/@FOX13TampaBay/live",
                "embed_url": None,
                "is_local": True,
            },
            {
                "name": "The Weather Channel",
                "description": "National weather coverage",
                "youtube_channel_url": "https://www.youtube.com/@weatherchannel",
                "live_url": "https://www.youtube.com/@weatherchannel/live",
                "embed_url": None,
                "is_local": False,
            },
        ]
    }
