# Aegis Backend — What Needs To Be Done

This document lists everything the backend team still needs to implement. Items are ordered by priority. Check off items as you complete them.

---

## PRIORITY 1: Live Data Feature (New)

The dashboard needs real-time storm monitoring and live news. This requires new endpoints that fetch from free government APIs.

### Task 1.1: Create `app/services/live_data_service.py`

This service fetches real-time data from free public APIs. No API keys needed for any of these.

```python
# app/services/live_data_service.py

import httpx
from datetime import datetime, timedelta

# ─── USGS Real-Time Water Levels ─────────────────────────────
# Tampa Bay area gauge stations
USGS_STATIONS = {
    "hillsborough_river": "02304500",   # Hillsborough River at Tampa
    "alafia_river": "02301500",         # Alafia River at Lithia
    "little_manatee": "02300500",       # Little Manatee River near Wimauma
    "palm_river": "02301990",           # Palm River near Tampa
}

async def get_water_levels() -> dict:
    """
    Fetch real-time water level (gauge height) from USGS Water Services API.
    Returns data for all Tampa Bay area stations.

    API docs: https://waterservices.usgs.gov/docs/instantaneous-values/

    URL format:
      https://waterservices.usgs.gov/nwis/iv/
        ?sites=02304500,02301500,02300500,02301990
        &parameterCd=00065          (gauge height in feet)
        &period=P1D                 (last 24 hours)
        &format=json

    Response parsing:
      response["value"]["timeSeries"] is a list.
      Each item has:
        - sourceInfo.siteName (e.g., "HILLSBOROUGH RIVER AT TAMPA FL")
        - sourceInfo.geoLocation.geogLocation.latitude / longitude
        - values[0].value[] — list of {value, dateTime} readings

    Return format:
      {
        "stations": [
          {
            "station_id": "02304500",
            "name": "Hillsborough River at Tampa",
            "lat": 27.9461,
            "lng": -82.4612,
            "current_level_ft": 4.2,
            "trend": "rising",           # rising, falling, stable
            "change_1h": +0.3,           # change in last hour
            "readings_24h": [            # for chart
              {"time": "2026-03-28T06:00:00", "value": 3.1},
              {"time": "2026-03-28T06:15:00", "value": 3.2},
              ...
            ],
            "flood_stage_ft": 12.0,      # hardcode from USGS flood stage data
            "percent_of_flood": 35.0,    # current_level / flood_stage * 100
            "last_updated": "2026-03-28T15:30:00"
          }
        ],
        "fetched_at": "2026-03-28T15:31:00"
      }

    Flood stages (hardcode these — from USGS):
      02304500 (Hillsborough River): flood stage = 12.0 ft
      02301500 (Alafia River): flood stage = 15.0 ft
      02300500 (Little Manatee): flood stage = 11.0 ft
      02301990 (Palm River): flood stage = 8.0 ft

    Trend calculation:
      Compare latest reading to reading 1 hour ago.
      If difference > +0.1 → "rising"
      If difference < -0.1 → "falling"
      Else → "stable"
    """
    pass


# ─── NOAA Tides & Currents ───────────────────────────────────

async def get_tide_data() -> dict:
    """
    Fetch real-time and predicted tide levels from NOAA CO-OPS API.
    Station: 8726520 (St. Petersburg, Tampa Bay)

    API docs: https://api.tidesandcurrents.noaa.gov/api/prod/

    Two calls needed:

    1. Observed water level (what's happening now):
       https://api.tidesandcurrents.noaa.gov/api/prod/datagetter
         ?station=8726520
         &product=water_level
         &datum=MLLW
         &units=english
         &time_zone=lst_ldt
         &format=json
         &date=latest
         &range=24          (last 24 hours)

    2. Tide predictions (high/low times):
       https://api.tidesandcurrents.noaa.gov/api/prod/datagetter
         ?station=8726520
         &product=predictions
         &datum=MLLW
         &units=english
         &time_zone=lst_ldt
         &format=json
         &begin_date=YYYYMMDD
         &end_date=YYYYMMDD
         &interval=hilo      (only high/low points)

    Response parsing (water_level):
      response["data"] is a list of {"t": "2026-03-28 15:00", "v": "1.234", "f": "0,0,0,0"}
      "v" is water level in feet above MLLW
      "t" is timestamp

    Response parsing (predictions):
      response["predictions"] is a list of {"t": "...", "v": "...", "type": "H" or "L"}
      "H" = high tide, "L" = low tide

    Return format:
      {
        "station": "St. Petersburg, FL",
        "current_level_ft": 1.8,
        "datum": "MLLW",
        "observations_24h": [
          {"time": "2026-03-28T06:00:00", "level_ft": 0.9},
          ...
        ],
        "next_high_tide": {"time": "2026-03-28T18:45:00", "level_ft": 2.3},
        "next_low_tide": {"time": "2026-03-29T00:30:00", "level_ft": 0.2},
        "tide_predictions": [
          {"time": "...", "level_ft": 2.3, "type": "high"},
          {"time": "...", "level_ft": 0.2, "type": "low"},
          ...
        ],
        "fetched_at": "2026-03-28T15:31:00"
      }
    """
    pass


# ─── NWS Current Weather Observation ─────────────────────────

async def get_current_weather() -> dict:
    """
    Fetch latest weather observation from NWS API.
    Station: KTPA (Tampa International Airport)

    API docs: https://www.weather.gov/documentation/services-web-api

    URL: https://api.weather.gov/stations/KTPA/observations/latest
    Headers: {"User-Agent": "Aegis-StormIntel (hackusf2026@example.com)"}
    Note: NWS API REQUIRES a User-Agent header or it returns 403.

    Response parsing:
      data = response["properties"]
      - data["temperature"]["value"]        → Celsius (convert to F)
      - data["windSpeed"]["value"]           → km/h (convert to mph)
      - data["windGust"]["value"]            → km/h (convert to mph), can be null
      - data["windDirection"]["value"]       → degrees (convert to cardinal: N, NE, E, etc.)
      - data["barometricPressure"]["value"]  → Pascals (convert to inHg: divide by 3386.39)
      - data["relativeHumidity"]["value"]    → percentage
      - data["textDescription"]             → "Partly Cloudy", "Rain", etc.
      - data["timestamp"]                   → ISO timestamp

    Conversion helpers:
      C to F: (celsius * 9/5) + 32
      km/h to mph: kmh * 0.621371
      Pascals to inHg: pascals / 3386.39
      Degrees to cardinal: 0=N, 45=NE, 90=E, 135=SE, 180=S, 225=SW, 270=W, 315=NW

    Return format:
      {
        "station": "Tampa International Airport",
        "temperature_f": 82.4,
        "wind_speed_mph": 45.2,
        "wind_gust_mph": 62.0,        # null if no gusts
        "wind_direction": "NE",
        "wind_direction_degrees": 45,
        "barometric_pressure_inhg": 29.85,
        "humidity_percent": 78.5,
        "conditions": "Rain",
        "observed_at": "2026-03-28T15:00:00",
        "fetched_at": "2026-03-28T15:31:00"
      }
    """
    pass


# ─── NWS Active Alerts ───────────────────────────────────────

async def get_active_alerts() -> dict:
    """
    Fetch active weather alerts for Hillsborough County from NWS.

    URL: https://api.weather.gov/alerts/active?zone=FLC057
    Headers: {"User-Agent": "Aegis-StormIntel (hackusf2026@example.com)"}

    FLC057 = Hillsborough County, FL zone code

    Response parsing:
      response["features"] is a list of GeoJSON features.
      Each feature["properties"] has:
        - event: "Hurricane Warning", "Flood Watch", "Tornado Warning", etc.
        - headline: one-line summary
        - description: full text
        - severity: "Extreme", "Severe", "Moderate", "Minor", "Unknown"
        - urgency: "Immediate", "Expected", "Future", "Past", "Unknown"
        - certainty: "Observed", "Likely", "Possible", "Unlikely", "Unknown"
        - onset: ISO timestamp when it starts
        - expires: ISO timestamp when it expires
        - senderName: "NWS Tampa Bay Ruskin FL"
        - areaDesc: affected areas text

    Return format:
      {
        "zone": "Hillsborough County, FL",
        "active_count": 3,
        "alerts": [
          {
            "event": "Hurricane Warning",
            "headline": "Hurricane Warning issued March 28...",
            "description": "...full text...",
            "severity": "Extreme",
            "urgency": "Immediate",
            "onset": "2026-03-28T12:00:00",
            "expires": "2026-03-29T12:00:00",
            "sender": "NWS Tampa Bay Ruskin FL",
            "areas": "Hillsborough; Pinellas; Pasco"
          },
          ...
        ],
        "fetched_at": "2026-03-28T15:31:00"
      }
    """
    pass


# ─── NWS Forecast ────────────────────────────────────────────

async def get_forecast() -> dict:
    """
    Fetch 7-day forecast for Tampa from NWS.

    Two-step process:
    1. Get forecast URL: GET https://api.weather.gov/points/27.9506,-82.4572
       Response has properties.forecast URL
    2. GET that forecast URL

    Headers: {"User-Agent": "Aegis-StormIntel (hackusf2026@example.com)"}

    Response parsing (step 2):
      response["properties"]["periods"] is a list of forecast periods.
      Each period has:
        - name: "Tonight", "Saturday", "Saturday Night", etc.
        - temperature: integer
        - temperatureUnit: "F"
        - windSpeed: "15 to 25 mph"
        - windDirection: "NE"
        - shortForecast: "Showers And Thunderstorms"
        - detailedForecast: full text paragraph
        - isDaytime: true/false

    Return format:
      {
        "location": "Tampa, FL",
        "periods": [
          {
            "name": "Tonight",
            "temperature_f": 75,
            "wind_speed": "15 to 25 mph",
            "wind_direction": "NE",
            "short_forecast": "Showers And Thunderstorms",
            "detailed_forecast": "...full text...",
            "is_daytime": false
          },
          ...
        ],
        "fetched_at": "2026-03-28T15:31:00"
      }
    """
    pass


# ─── News Aggregation ────────────────────────────────────────

async def get_news_feed() -> dict:
    """
    Aggregate storm/weather news from multiple trusted RSS/Atom feeds.

    Sources (all free, no auth):

    1. NWS Tampa Bay RSS:
       https://alerts.weather.gov/cap/wwaatmget.php?x=FLC057&y=1
       Format: Atom/CAP XML
       Parse: Use xml.etree.ElementTree
       Namespace: {urn:oasis:names:tc:emergency:cap:1.2}
       Each <entry> has <title>, <summary>, <updated>, <link>

    2. USGS Water Alert RSS for Florida:
       https://water.usgs.gov/wateralert/feeds/FL.xml
       Format: RSS 2.0 XML
       Each <item> has <title>, <description>, <pubDate>, <link>
       Filter items containing "Tampa" or "Hillsborough" or station IDs

    3. NHC Atlantic Tropical Cyclones RSS:
       https://www.nhc.noaa.gov/index-at.xml
       Format: RSS 2.0 XML
       Each <item> has <title>, <description>, <pubDate>, <link>
       Filter for active storms affecting Gulf of Mexico / Florida

    4. FEMA Disaster Declarations RSS:
       https://www.fema.gov/api/open/v2/DisasterDeclarationsSummaries?$filter=state eq 'FL'&$orderby=declarationDate desc&$top=5
       Format: JSON (not RSS)
       Returns recent FEMA disaster declarations for Florida

    Parsing approach:
      For RSS/Atom feeds, use httpx to fetch + xml.etree.ElementTree to parse.
      For FEMA, use httpx + json.

      Normalize all items to a common format and sort by date (newest first).
      Limit to 20 most recent items.
      Deduplicate by title similarity.

    Return format:
      {
        "items": [
          {
            "source": "NWS Tampa Bay",
            "title": "Hurricane Warning for Hillsborough County",
            "summary": "A hurricane warning has been issued...",
            "url": "https://alerts.weather.gov/...",
            "published_at": "2026-03-28T14:00:00",
            "severity": "extreme",       # from NWS: extreme, severe, moderate, minor
            "category": "hurricane"      # hurricane, flood, tornado, thunderstorm, other
          },
          {
            "source": "USGS Water Alert",
            "title": "Hillsborough River above flood stage",
            "summary": "...",
            "url": "https://water.usgs.gov/...",
            "published_at": "2026-03-28T13:00:00",
            "severity": "severe",
            "category": "flood"
          },
          ...
        ],
        "source_count": 4,
        "total_items": 15,
        "fetched_at": "2026-03-28T15:31:00"
      }

    Category detection (from title/summary text):
      Contains "hurricane" or "tropical" → "hurricane"
      Contains "flood" or "water level" or "surge" → "flood"
      Contains "tornado" → "tornado"
      Contains "thunder" or "lightning" → "thunderstorm"
      Else → "other"
    """
    pass


# ─── Live Stream URLs ────────────────────────────────────────

def get_live_streams() -> dict:
    """
    Return hardcoded YouTube live stream URLs for Tampa Bay news stations.
    These are the channels that go live during storms.

    No API call needed — just return the data.

    Return format:
      {
        "streams": [
          {
            "name": "Bay News 9",
            "description": "Spectrum Bay News 9 — Tampa Bay's 24/7 local news",
            "youtube_channel_url": "https://www.youtube.com/@BayNews9",
            "live_url": "https://www.youtube.com/@BayNews9/live",
            "embed_url": null,
            "is_local": true
          },
          {
            "name": "WFLA News Channel 8",
            "description": "NBC affiliate — Tampa Bay storm coverage",
            "youtube_channel_url": "https://www.youtube.com/@WFLANewsChannel8",
            "live_url": "https://www.youtube.com/@WFLANewsChannel8/live",
            "embed_url": null,
            "is_local": true
          },
          {
            "name": "FOX 13 Tampa Bay",
            "description": "FOX affiliate — Tampa Bay weather and storm tracking",
            "youtube_channel_url": "https://www.youtube.com/@FOX13TampaBay",
            "live_url": "https://www.youtube.com/@FOX13TampaBay/live",
            "embed_url": null,
            "is_local": true
          },
          {
            "name": "The Weather Channel",
            "description": "National weather coverage",
            "youtube_channel_url": "https://www.youtube.com/@weatherchannel",
            "live_url": "https://www.youtube.com/@weatherchannel/live",
            "embed_url": null,
            "is_local": false
          }
        ]
      }

    Note: embed_url is null because YouTube live streams don't have stable
    embed URLs. The frontend will link to the /live page instead.
    """
    pass
```

### Task 1.2: Create `app/api/routes_live.py`

New route file with these endpoints:

```python
# app/api/routes_live.py

# GET /api/v1/live/water-levels
#   → calls get_water_levels()
#   → returns water gauge data for all Tampa Bay stations
#   → cache for 60 seconds (store in memory dict with timestamp)

# GET /api/v1/live/tides
#   → calls get_tide_data()
#   → returns tide observations + predictions
#   → cache for 60 seconds

# GET /api/v1/live/weather
#   → calls get_current_weather()
#   → returns current NWS observation
#   → cache for 60 seconds

# GET /api/v1/live/forecast
#   → calls get_forecast()
#   → returns 7-day NWS forecast
#   → cache for 30 minutes (forecast doesn't change often)

# GET /api/v1/live/alerts
#   → calls get_active_alerts()
#   → returns active NWS severe weather alerts for Hillsborough County
#   → cache for 60 seconds

# GET /api/v1/live/news
#   → calls get_news_feed()
#   → returns aggregated news from NWS RSS + USGS RSS + NHC RSS + FEMA API
#   → cache for 2 minutes (news changes less frequently)

# GET /api/v1/live/streams
#   → calls get_live_streams()
#   → returns hardcoded YouTube live stream URLs
#   → no cache needed (static data)

# GET /api/v1/live/all
#   → calls ALL of the above in parallel using asyncio.gather()
#   → returns combined response with all live data
#   → this is the main endpoint the frontend polls every 60 seconds
#   → if any individual fetch fails, return partial data with error field

# Simple in-memory cache implementation:
# _cache = {}
# async def cached_fetch(key: str, fetch_fn, ttl_seconds: int):
#     now = time.time()
#     if key in _cache and now - _cache[key]["time"] < ttl_seconds:
#         return _cache[key]["data"]
#     data = await fetch_fn()
#     _cache[key] = {"data": data, "time": now}
#     return data
```

### Task 1.3: Register routes in `app/main.py`

Add to imports:
```python
from app.api import routes_live
```

Add to router registration:
```python
app.include_router(routes_live.router, prefix=PREFIX)
```

### Task 1.4: Add `httpx` to `requirements.txt`

Add `httpx` for async HTTP calls (if not already present).

---

## PRIORITY 2: Recovery Brief Generation (Missing Feature)

The `recovery_briefs` table exists, the GET endpoints exist, but **nothing writes to this table**. The post-storm phase is empty without this.

### Task 2.1: Create recovery brief generation

Two options (pick one):

**Option A: Add to orchestrator pipeline (preferred)**

In `app/agents/orchestrator.py`, add a recovery step to the post-storm pipeline that uses Gemini to generate briefs by summarizing current data per neighborhood.

The function should:
1. Query current incidents, resources, and alerts for each neighborhood
2. Call Gemini with a prompt like: "Generate a recovery brief for {neighborhood} based on: {incidents}, {resources}, {alerts}"
3. Save the generated brief to `recovery_briefs` table

**Option B: Standalone endpoint**

Add `POST /api/v1/recovery/generate` that:
1. For each neighborhood in `tampa_zones.json`, query all related data
2. Use Gemini to summarize into a brief
3. Insert into `recovery_briefs` table
4. Return the generated briefs

### Task 2.2: Recovery brief fields to generate

Each brief should have:
```json
{
  "neighborhood": "Seminole Heights",
  "power_status": "Estimated restoration 48-72 hours — Duke Energy crew dispatched",
  "water_status": "Boil water advisory in effect until further notice",
  "roads_status": "Nebraska Ave passable. Florida Ave blocked between Osborne and Hanna",
  "shelters_nearby": "[JSON array of nearby open shelter IDs]",
  "medical_nearby": "[JSON array of nearby medical resource IDs]",
  "key_updates": "[\"National Guard distributing water at Copeland Park\", \"Debris pickup begins Monday\"]"
}
```

---

## PRIORITY 3: Match Review Endpoint (Missing Feature)

The `matches` table has `status` and `reviewed_by` columns, but there's no endpoint to update them.

### Task 3.1: Add PATCH endpoint

In `app/api/routes_reunification.py`, add:

```python
# PATCH /api/v1/reunification/matches/{match_id}
# Body: { "status": "confirmed" | "rejected", "reviewed_by": "operator_name" }
#
# When status = "confirmed":
#   1. Update match status to "confirmed"
#   2. Update missing_persons.status to "found" for the matched person
#   3. Update found_persons.matched_missing_id to the missing person's ID
#
# When status = "rejected":
#   1. Update match status to "rejected"
#   2. No changes to missing_persons or found_persons
#
# Return the updated match record
```

---

## PRIORITY 4: Health Check Endpoint

### Task 4.1: Add `/health` endpoint

In `app/main.py`, add:

```python
@app.get("/health")
async def health():
    return {"status": "healthy", "timestamp": datetime.utcnow().isoformat()}
```

---

## PRIORITY 5: Nice-to-Have Improvements

These are not critical but would help during the demo:

### Task 5.1: Add pagination to GET endpoints

Add optional `limit` and `offset` query params to:
- `GET /reports` (default limit=50)
- `GET /alerts` (default limit=50)
- `GET /incidents` (default limit=50)

### Task 5.2: Add ElevenLabs voice service back

Create `app/services/elevenlabs_service.py` if going for the MLH ElevenLabs prize:
```python
# Use ElevenLabs API to generate a voice alert audio file
# POST https://api.elevenlabs.io/v1/text-to-speech/{voice_id}
# Returns MP3 audio
# Save to /tmp/ and serve via a static file endpoint
```

### Task 5.3: Test all agents end-to-end

Run the backend locally and verify:
1. `POST /phase/set` with `{"phase": "pre_storm"}` → succeeds
2. `POST /phase/orchestrate` → Monitor + Alert agents run without error
3. `POST /phase/set` with `{"phase": "active_storm"}` → succeeds
4. `POST /reports` with a field report → saves to DB
5. `POST /reports/process` → Field Report Agent parses it
6. `POST /incidents/rank` → Severity Agent scores it
7. `POST /phase/set` with `{"phase": "post_storm"}` → succeeds
8. `POST /reunification/match` → Reunification Agent finds matches
9. All `GET` endpoints return correct data

---

## Summary Checklist

```
[ ] 1.1  Create live_data_service.py (water levels, tides, weather, alerts, news, streams)
[ ] 1.2  Create routes_live.py (7 endpoints + /live/all combined endpoint)
[ ] 1.3  Register routes_live in main.py
[ ] 1.4  Add httpx to requirements.txt
[ ] 2.1  Recovery brief generation (agent or standalone endpoint)
[ ] 2.2  Verify recovery briefs save correctly
[ ] 3.1  PATCH /reunification/matches/:id endpoint
[ ] 4.1  Health check endpoint
[ ] 5.1  Pagination on GET endpoints (optional)
[ ] 5.2  ElevenLabs voice service (optional — for MLH prize)
[ ] 5.3  End-to-end agent testing
```
