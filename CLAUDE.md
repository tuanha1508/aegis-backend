# Aegis Backend — Context for Contributors

## What is Aegis?

Aegis is a multi-agent disaster intelligence platform for Tampa Bay built for HackUSF 2026. It covers the full storm lifecycle: pre-storm monitoring → active storm response → post-storm recovery. The backend is the brain — it runs 6 AI agents via Google ADK, serves a REST API via FastAPI, and persists data in **PostgreSQL** (typically **Supabase** in production via `DATABASE_URL`).

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
- PostgreSQL for database (**psycopg**; schema in `supabase/migrations/`)
- Twilio for SMS (incoming field reports + outgoing alerts)
- ElevenLabs for voice alert generation

## Project Structure

```
aegis-backend/
├── app/
│   ├── main.py                  # FastAPI entry point, CORS, mount routers, lifespan init_db
│   ├── config.py                # Env vars: GEMINI_API_KEY, GROQ_API_KEY, TWILIO_*, DATABASE_URL, ...
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
│   │   ├── routes_assignments.py
│   │   ├── routes_audit.py      # Agent audit log
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
│   │   ├── database.py          # Postgres (psycopg): init_db(), get_connection()
│   │   ├── audit.py             # insert_audit_log() for agent-trigger routes
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
├── supabase/
│   └── migrations/              # Canonical Postgres DDL (applied by init_db)
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
- **Writes to:** `reports` table (sets `processed` to true when parsed)

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

## Database schema

The database is **PostgreSQL** (e.g. Supabase). **Do not assume SQLite.**

- **Canonical DDL:** `supabase/migrations/` — `BIGSERIAL`, `BOOLEAN`, `TIMESTAMPTZ`, etc.
- **Runtime:** `app/db/database.py` uses **psycopg**; `init_db()` applies migrations on app startup; `get_connection()` is used by API routes and agent tools.
- **Tables:** `phase`, `risk_assessments`, `alerts`, `reports`, `incidents`, `resources`, `missing_persons`, `found_persons`, `matches`, `recovery_briefs`, `audit_log`, `assignments` (see migrations for exact columns and constraints).

When writing SQL in agents, use Postgres semantics (e.g. `TRUE`/`FALSE`, `NOW()` where the schema expects it).

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
POST   /alerts/generate              → trigger Alert Agent (response includes `run_id`, audit logged)

# Reports (Active Storm)
GET    /reports                      → all field reports
POST   /reports                      → submit new report { "text": "...", "source": "app" }
POST   /reports/process              → trigger Field Report Agent (response includes `run_id`, audit logged)

# Incidents
GET    /incidents                    → severity-ranked incidents (optional ?severity=critical)
POST   /incidents/rank               → trigger Severity Agent (response includes `run_id`, audit logged)

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
POST   /reunification/match          → trigger Reunification Agent (response includes `run_id`, audit logged)

# Recovery
GET    /recovery/briefs              → all neighborhood recovery briefs
GET    /recovery/briefs/:neighborhood → specific brief

# SMS
POST   /sms/webhook                  → Twilio incoming SMS webhook

# Audit / assignments
GET    /audit-log                    → agent audit log (?run_id, ?limit)
GET    /assignments                  → list assignments (?incident_id)
GET    /assignments/{id}             → single assignment
# (additional POST/PATCH on assignments — see routes_assignments.py)
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

See `.env.example` for the full list. Important:

```
GEMINI_API_KEY=your_gemini_api_key
GROQ_API_KEY=                    # optional — LiteLLM / Groq for ADK when set
TWILIO_ACCOUNT_SID=your_twilio_sid
TWILIO_AUTH_TOKEN=your_twilio_token
TWILIO_PHONE_NUMBER=+1XXXXXXXXXX
ELEVENLABS_API_KEY=your_elevenlabs_key
DATABASE_URL=postgresql://...    # Supabase Postgres URI (required for app DB access)
DEMO_MODE=true                   # sample weather vs live placeholder
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

1. **First:** FastAPI setup + Postgres migrations + seed data (Person A)
2. **Second:** Monitor Agent + Alert Agent (Person A), Field Report Agent + Severity Agent (Person B)
3. **Third:** Resource Agent + Reunification Agent (Person B)
4. **Fourth:** Twilio webhook + ElevenLabs voice (Person B)
5. **Last:** Polish, edge cases, demo hardening

## Frontend Repo

The frontend is at: https://github.com/tuanha1508/aegis-frontend
It connects to this backend via the API endpoints listed above.
The frontend expects JSON responses matching the Pydantic models in `app/models/`.
CORS must allow the frontend origin (localhost:3000 for dev, Vercel URL for prod).
