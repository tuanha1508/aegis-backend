"""Live data endpoints — real-time weather, water levels, alerts, news."""

import asyncio
import time

from fastapi import APIRouter

from app.services.live_data_service import (
    get_active_alerts,
    get_current_weather,
    get_forecast,
    get_live_streams,
    get_news_feed,
    get_tide_data,
    get_water_levels,
)

router = APIRouter(tags=["live"])

# Simple in-memory cache
_cache: dict[str, dict] = {}


async def _cached(key: str, fetch_fn, ttl_seconds: int):
    now = time.time()
    if key in _cache and now - _cache[key]["time"] < ttl_seconds:
        return _cache[key]["data"]
    data = await fetch_fn()
    _cache[key] = {"data": data, "time": now}
    return data


@router.get("/live/water-levels")
async def live_water_levels():
    return await _cached("water_levels", get_water_levels, 60)


@router.get("/live/tides")
async def live_tides():
    return await _cached("tides", get_tide_data, 60)


@router.get("/live/weather")
async def live_weather():
    return await _cached("weather", get_current_weather, 60)


@router.get("/live/forecast")
async def live_forecast():
    return await _cached("forecast", get_forecast, 1800)


@router.get("/live/alerts")
async def live_alerts():
    return await _cached("alerts", get_active_alerts, 60)


@router.get("/live/news")
async def live_news():
    return await _cached("news", get_news_feed, 120)


@router.get("/live/streams")
async def live_streams():
    return get_live_streams()


@router.get("/live/all")
async def live_all():
    """Fetch all live data in parallel — main endpoint for frontend polling."""
    keys = ["water_levels", "tides", "weather", "alerts", "news", "forecast"]
    fns = [get_water_levels, get_tide_data, get_current_weather,
           get_active_alerts, get_news_feed, get_forecast]
    ttls = [60, 60, 60, 60, 120, 1800]

    async def safe_fetch(key, fn, ttl):
        try:
            return key, await _cached(key, fn, ttl)
        except Exception as e:
            return key, {"error": str(e)}

    results = await asyncio.gather(
        *(safe_fetch(k, f, t) for k, f, t in zip(keys, fns, ttls))
    )

    response = {k: v for k, v in results}
    response["streams"] = get_live_streams()
    return response
