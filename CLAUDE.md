# Aegis Backend — Context for Contributors

## What is Aegis?

Aegis is a multi-agent disaster intelligence platform for Tampa Bay built for HackUSF 2026. It covers the full storm lifecycle: pre-storm monitoring → active storm response → post-storm recovery. The backend is the brain — it runs 6 AI agents via Google ADK, serves a REST API via FastAPI, and stores data in SQLite.

## Hackathon Requirements

- **Public GitHub repo** (this repo)
- **Google Cloud ADK sponsor challenge** ($1,750) — must use Google ADK for multi-agent orchestration
- **MLH Gemini API prize** — must use Gemini as the LLM
- **MLH ElevenLabs prize** — must use ElevenLabs for voice alerts
- **Code freeze: March 29, 2026 at 11:30 AM EDT**

## Tech Stack

- Python 3.11+
- Google ADK (Agent Development Kit) for multi-agent orchestration
- Gemini Flash (via Vertex AI or AI Studio) as the LLM for all agents
- FastAPI for REST API
- SQLite for database (single file, zero config)
- Twilio for SMS (incoming field reports + outgoing alerts)
- ElevenLabs for voice alert generation

## Project Structure

```
aegis-backend/
├── app/
│   ├── main.py                  # FastAPI entry point, CORS, mount routers
│   ├── config.py                # Env vars: GEMINI_API_KEY, TWILIO_*, ELEVENLABS_*
│   │
│   ├── api/                     # One file per resource
│   │   ├── routes_phase.py      # GET /phase, POST /phase/advance
│   │   ├── routes_monitor.py    # GET /monitor/risk, GET /monitor/weather
│   │   ├── routes_alerts.py     # GET /alerts, POST /alerts/generate
│   │   ├── routes_reports.py    # GET /reports, POST /reports
│   │   ├── routes_incidents.py  # GET /incidents, POST /incidents/rank
│   │   ├── routes_resources.py  # GET /resources, PUT /resources/:id
│   │   ├── routes_reunification.py  # GET/POST missing, found, matches
│   │   ├── routes_recovery.py   # GET /recovery/briefs
│   │   └── routes_sms.py       # POST /sms/webhook (Twilio)
│   │
│   ├── agents/                  # Google ADK agents
│   │   ├── orchestrator.py      # Parent agent that coordinates sub-agents
│   │   ├── monitor_agent.py     # Ingests weather data → risk scores
│   │   ├── alert_agent.py       # Risk/incident data → human-readable alerts
│   │   ├── field_report_agent.py    # Raw text → structured incident
│   │   ├── severity_agent.py    # Structured incidents → urgency ranking
│   │   ├── resource_agent.py    # Tracks shelters, supplies, routes
│   │   └── reunification_agent.py   # Missing + found → match with confidence
│   │
│   ├── models/                  # Pydantic models for request/response
│   │   ├── phase.py
│   │   ├── alert.py
│   │   ├── report.py
│   │   ├── incident.py
│   │   ├── resource.py
│   │   └── person.py
│   │
│   ├── db/
│   │   ├── database.py          # SQLite init, get_connection()
│   │   └── seed.py              # Seed Tampa Bay demo data
│   │
│   ├── services/
│   │   ├── twilio_service.py    # send_sms(), handle incoming
│   │   ├── elevenlabs_service.py    # generate_voice_alert()
│   │   └── weather_service.py   # Fetch/load NOAA data
│   │
│   └── data/                    # Static seed data files
│       ├── tampa_shelters.json
│       ├── tampa_zones.json
│       ├── sample_weather.json
│       ├── sample_reports.json
│       └── sample_persons.json
│
├── requirements.txt
├── .env.example
└── README.md
```

## The 6 Agents — What Each One Does

### 1. Monitor Agent (Pre-Storm)
- **Input:** NOAA weather JSON, USGS water levels, Tampa evacuation zones
- **Processing:** Uses Gemini to analyze storm trajectory, calculate per-neighborhood flood risk
- **Output:** List of neighborhoods with risk scores (0-1), storm surge estimates, evacuation recommendations
- **Writes to:** `risk_assessments` table

### 2. Alert Agent (Pre-Storm + Active Storm)
- **Input:** Risk data from Monitor Agent OR incident data from Severity Agent
- **Processing:** Uses Gemini to generate plain-language warnings, translates to Spanish
- **Output:** Alert objects with priority (info/warning/critical/emergency), sends via Twilio SMS + ElevenLabs voice
- **Writes to:** `alerts` table

### 3. Field Report Agent (Active Storm)
- **Input:** Raw text from SMS (Twilio webhook) or app form submission
- **Processing:** Uses Gemini to extract location, incident type, people count, language detection, geocoding
- **Output:** Structured report with parsed fields
- **Writes to:** `reports` table (updates processed=1)

### 4. Severity Agent (Active Storm)
- **Input:** Processed reports from Field Report Agent
- **Processing:** Uses Gemini to score urgency 0-100, considers life threat, children/elderly, water rise rate, resource proximity. Consolidates duplicate reports.
- **Output:** Ranked incident list with severity scores and recommended actions
- **Writes to:** `incidents` table

### 5. Resource Agent (Active + Post-Storm)
- **Input:** Pre-seeded resource database + incoming updates (capacity changes, road closures)
- **Processing:** Tracks shelter capacity, finds nearest resources by type and location, factors in road accessibility
- **Output:** Resource list with real-time status
- **Writes to:** `resources` table (updates status, occupancy)

### 6. Reunification Agent (Post-Storm)
- **Input:** Missing person reports + found/shelter check-in records
- **Processing:** Uses Gemini for fuzzy name matching, physical description comparison, location plausibility analysis
- **Output:** Match candidates with confidence scores (0-1) and match factor explanations
- **Writes to:** `matches` table

## Database Schema

```sql
CREATE TABLE phase (
    id INTEGER PRIMARY KEY DEFAULT 1,
    current_phase TEXT NOT NULL DEFAULT 'pre_storm',
    started_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE risk_assessments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    neighborhood TEXT NOT NULL,
    zone TEXT,
    lat REAL NOT NULL,
    lng REAL NOT NULL,
    flood_risk REAL,
    storm_surge_ft REAL,
    time_to_impact_hours REAL,
    recommendation TEXT,
    evacuate_by TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE alerts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    phase TEXT NOT NULL,
    priority TEXT NOT NULL,
    neighborhood TEXT,
    title TEXT NOT NULL,
    message TEXT NOT NULL,
    message_es TEXT,
    channels TEXT,
    delivered INTEGER DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE reports (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    raw_text TEXT NOT NULL,
    source TEXT NOT NULL,
    sender_phone TEXT,
    location_text TEXT,
    lat REAL,
    lng REAL,
    incident_type TEXT,
    people_mentioned INTEGER,
    has_children INTEGER DEFAULT 0,
    language TEXT DEFAULT 'en',
    processed INTEGER DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE incidents (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    report_ids TEXT,
    incident_type TEXT NOT NULL,
    location_text TEXT,
    lat REAL NOT NULL,
    lng REAL NOT NULL,
    severity_score INTEGER,
    severity_label TEXT,
    factors TEXT,
    recommended_action TEXT,
    verified INTEGER DEFAULT 0,
    report_count INTEGER DEFAULT 1,
    resolved INTEGER DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE resources (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    type TEXT NOT NULL,
    name TEXT NOT NULL,
    lat REAL NOT NULL,
    lng REAL NOT NULL,
    address TEXT,
    capacity INTEGER,
    current_occupancy INTEGER DEFAULT 0,
    amenities TEXT,
    status TEXT DEFAULT 'open',
    notes TEXT,
    last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE missing_persons (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    reported_by TEXT NOT NULL,
    reporter_phone TEXT,
    name TEXT NOT NULL,
    age INTEGER,
    gender TEXT,
    description TEXT,
    last_known_location TEXT,
    last_known_lat REAL,
    last_known_lng REAL,
    last_contact TIMESTAMP,
    status TEXT DEFAULT 'missing',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE found_persons (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    age_approx INTEGER,
    gender TEXT,
    description TEXT,
    found_at TEXT,
    found_lat REAL,
    found_lng REAL,
    checked_in TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    matched_missing_id INTEGER,
    FOREIGN KEY (matched_missing_id) REFERENCES missing_persons(id)
);

CREATE TABLE matches (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    missing_id INTEGER NOT NULL,
    found_id INTEGER NOT NULL,
    confidence REAL NOT NULL,
    match_factors TEXT,
    status TEXT DEFAULT 'pending',
    reviewed_by TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (missing_id) REFERENCES missing_persons(id),
    FOREIGN KEY (found_id) REFERENCES found_persons(id)
);

CREATE TABLE recovery_briefs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    neighborhood TEXT NOT NULL,
    power_status TEXT,
    water_status TEXT,
    roads_status TEXT,
    shelters_nearby TEXT,
    medical_nearby TEXT,
    key_updates TEXT,
    generated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

## API Endpoints

All endpoints prefixed with `/api/v1`.

```
# Phase
GET    /phase                        → current phase state
POST   /phase/advance                → move to next phase
POST   /phase/set                    → set specific phase { "phase": "active_storm" }

# Monitor (Pre-Storm)
GET    /monitor/risk                 → all neighborhood risk assessments
GET    /monitor/weather              → storm data and trajectory

# Alerts
GET    /alerts                       → all alerts (optional ?priority=critical)
POST   /alerts/generate              → trigger Alert Agent

# Reports (Active Storm)
GET    /reports                      → all field reports
POST   /reports                      → submit new report { "text": "...", "source": "app" }
POST   /reports/process              → trigger Field Report Agent on unprocessed reports

# Incidents
GET    /incidents                    → severity-ranked incidents (optional ?severity=critical)
POST   /incidents/rank               → trigger Severity Agent

# Resources
GET    /resources                    → all resources (optional ?type=shelter)
GET    /resources/nearest            → nearest resource ?lat=X&lng=Y&type=shelter
PUT    /resources/:id                → update resource status/capacity

# Reunification
GET    /reunification/missing        → all missing person reports
POST   /reunification/missing        → report missing person
GET    /reunification/found          → all found person records
POST   /reunification/found          → report found person
GET    /reunification/matches        → all matches with confidence scores
POST   /reunification/match          → trigger Reunification Agent

# Recovery
GET    /recovery/briefs              → all neighborhood recovery briefs
GET    /recovery/briefs/:neighborhood → specific brief

# SMS
POST   /sms/webhook                  → Twilio incoming SMS webhook
```

## Seed Data (Tampa Bay)

Use real Tampa Bay locations for the demo:

**Shelters:**
- First Baptist Church of Tampa (27.9506, -82.4572) — capacity 200
- USF Marshall Center (28.0587, -82.4137) — capacity 350
- Hillsborough High School (27.9686, -82.4620) — capacity 150
- Tampa Convention Center (27.9425, -82.4584) — capacity 500

**High-risk neighborhoods:**
- Palma Ceia (27.9234, -82.4968) — Zone A, high flood risk
- Davis Islands (27.9210, -82.4630) — Zone A, high flood risk
- Channelside (27.9430, -82.4490) — Zone A, high flood risk
- South Tampa (27.9100, -82.4900) — Zone A, high flood risk
- Hyde Park (27.9400, -82.4750) — Zone B, moderate flood risk
- Seminole Heights (27.9945, -82.4572) — Zone C, lower flood risk
- Temple Terrace (28.0350, -82.3890) — Zone C, lower flood risk
- Ybor City (27.9600, -82.4370) — Zone B, moderate flood risk

**Demo scenario — Reunification story:**
- Missing: Maria Garcia, 72, female, "short gray hair, glasses, uses a walker", last seen Davis Islands
- Found: "Maria G.", ~70, female, "elderly woman with walker, Spanish speaking", checked in at First Baptist Church
- Expected match confidence: ~89%

**Demo scenario — Field reports:**
- "Flooding on Bay to Bay Blvd, water entering homes"
- "Tree down on Dale Mabry blocking both lanes near Gandy"
- "Power out in all of Seminole Heights since 2am"
- "Family trapped on second floor, Henderson Blvd, 2 adults 2 children"
- "Hillsborough High shelter needs more water and blankets"

## Environment Variables

```
GEMINI_API_KEY=your_gemini_api_key
TWILIO_ACCOUNT_SID=your_twilio_sid
TWILIO_AUTH_TOKEN=your_twilio_token
TWILIO_PHONE_NUMBER=+1XXXXXXXXXX
ELEVENLABS_API_KEY=your_elevenlabs_key
DATABASE_URL=sqlite:///aegis.db
```

## How to Run

```bash
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env  # fill in API keys
python -m app.db.seed  # seed demo data
uvicorn app.main:app --reload --port 8000
```

## Priority Order for Building

1. **First:** FastAPI setup + SQLite schema + seed data (Person A)
2. **Second:** Monitor Agent + Alert Agent (Person A), Field Report Agent + Severity Agent (Person B)
3. **Third:** Resource Agent + Reunification Agent (Person B)
4. **Fourth:** Twilio webhook + ElevenLabs voice (Person B)
5. **Last:** Polish, edge cases, demo hardening

## Frontend Repo

The frontend is at: https://github.com/tuanha1508/aegis-frontend
It connects to this backend via the API endpoints listed above.
The frontend expects JSON responses matching the Pydantic models in `app/models/`.
CORS must allow the frontend origin (localhost:3000 for dev, Vercel URL for prod).
