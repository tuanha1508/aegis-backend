# Aegis — Full System Architecture

## System Overview

```
┌─────────────────────────────────────────────────────────────────────┐
│                          USERS                                      │
│  Browser (Dashboard)    SMS                                         │
└──────────┬──────────────────┬──────────────────┬────────────────────┘
           │                  │                  │
           ▼                  ▼                  ▼
┌─────────────────────┐  ┌──────────────────────────────────────────┐
│   NEXT.JS FRONTEND  │  │           FASTAPI BACKEND                │
│   (Vercel)          │  │           (Render/Railway)               │
│                     │  │                                          │
│  /                  │  │  /api/v1/                                │
│  Dashboard home     │◄►│    /phase         GET current phase      │
│  with phase tabs    │  │    /phase/advance  POST transition phase  │
│                     │  │    /monitor        GET risk data          │
│  /map               │  │    /alerts         GET/POST alerts        │
│  Leaflet map with   │  │    /reports        GET/POST field reports │
│  risk zones +       │  │    /incidents      GET ranked incidents   │
│  markers            │  │    /resources      GET shelters/supplies  │
│                     │  │    /reunification  GET/POST missing/found │
│  /report            │  │    /recovery       GET neighborhood briefs│
│  Submit field       │  │    /sms/webhook    POST incoming SMS      │
│  reports            │  │                                          │
│                     │  │  ┌──────────────────────────────────┐    │
│  /reunify           │  │  │      GOOGLE ADK ORCHESTRATOR     │    │
│  Missing/found      │  │  │                                  │    │
│  person portal      │  │  │  ┌────────┐  ┌────────────────┐ │    │
│                     │  │  │  │Monitor │  │Alert Agent     │ │    │
│  /resources         │  │  │  │Agent   │  │                │ │    │
│  Shelter/supply     │  │  │  └────────┘  └────────────────┘ │    │
│  finder             │  │  │  ┌────────┐  ┌────────────────┐ │    │
│                     │  │  │  │Field   │  │Severity Agent  │ │    │
│  /recovery          │  │  │  │Report  │  │                │ │    │
│  Neighborhood       │  │  │  │Agent   │  └────────────────┘ │    │
│  briefs             │  │  │  └────────┘  ┌────────────────┐ │    │
│                     │  │  │  ┌────────┐  │Reunification   │ │    │
│                     │  │  │  │Resource│  │Agent           │ │    │
│                     │  │  │  │Agent   │  └────────────────┘ │    │
│                     │  │  │  └────────┘                     │    │
│                     │  │  └──────────────────────────────────┘    │
│                     │  │                                          │
│                     │  │  ┌──────────────────────────────────┐    │
│                     │  │  │   PostgreSQL (Supabase) Database  │    │
│                     │  │  └──────────────────────────────────┘    │
└─────────────────────┘  └──────────────────────────────────────────┘
```

---

## Phase System

The entire app revolves around three phases. The phase determines which agents are active and what the dashboard shows.

```
PHASE 1: PRE-STORM          PHASE 2: ACTIVE STORM         PHASE 3: POST-STORM
─────────────────           ──────────────────            ─────────────────
Agents active:              Agents active:                Agents active:
  - Monitor Agent             - Field Report Agent          - Resource Agent
  - Alert Agent               - Severity Agent              - Reunification Agent
                               - Resource Agent              - Recovery Planner
                               - Alert Agent                   (Gemini summarizer)

Dashboard shows:            Dashboard shows:              Dashboard shows:
  - Risk heat map             - Incoming reports            - Resource map
  - Weather data              - Ranked incidents            - Missing/found matches
  - Evacuation alerts         - Resource status             - Neighborhood briefs
  - Shelter pre-staging       - Live severity map           - Recovery timeline
```

Phase transitions can be triggered manually by an operator OR automatically based on conditions (e.g., wind speed exceeds threshold → Phase 2).

---

## Backend Architecture (Python + FastAPI + Google ADK)

### Directory Structure

```
aegis-backend/
├── app/
│   ├── __init__.py
│   ├── main.py                  # FastAPI app entry point
│   ├── config.py                # Environment variables, settings
│   │
│   ├── api/
│   │   ├── __init__.py
│   │   ├── routes_phase.py      # Phase management endpoints
│   │   ├── routes_monitor.py    # Weather/risk data endpoints
│   │   ├── routes_alerts.py     # Alert endpoints
│   │   ├── routes_reports.py    # Field report endpoints
│   │   ├── routes_incidents.py  # Severity-ranked incident endpoints
│   │   ├── routes_resources.py  # Shelter/supply endpoints
│   │   ├── routes_reunification.py  # Missing/found endpoints
│   │   ├── routes_recovery.py   # Recovery brief endpoints
│   │   ├── routes_assignments.py # Responder assignments (if enabled)
│   │   ├── routes_audit.py      # Agent audit log endpoints
│   │   └── routes_sms.py       # SMS webhook + chat endpoint
│   │
│   ├── agents/
│   │   ├── __init__.py
│   │   ├── orchestrator.py      # Main ADK orchestrator agent
│   │   ├── monitor_agent.py     # Weather data ingestion + risk scoring
│   │   ├── alert_agent.py       # Warning generation + delivery
│   │   ├── field_report_agent.py    # Report parsing + structuring
│   │   ├── severity_agent.py    # Urgency ranking
│   │   ├── resource_agent.py    # Resource tracking
│   │   └── reunification_agent.py   # Missing/found matching
│   │
│   ├── models/
│   │   ├── __init__.py
│   │   ├── phase.py             # Phase state model
│   │   ├── alert.py             # Alert data model
│   │   ├── report.py            # Field report data model
│   │   ├── incident.py          # Severity-ranked incident model
│   │   ├── resource.py          # Shelter/supply data model
│   │   └── person.py            # Missing/found person model
│   │
│   ├── db/
│   │   ├── __init__.py
│   │   ├── database.py          # psycopg Postgres connection + init_db()
│   │   ├── audit.py             # insert_audit_log() for agent runs
│   │   └── seed.py              # Seed Tampa Bay demo data
│   │
│   ├── services/
│   │   ├── __init__.py
│   │   └── weather_service.py   # NOAA data fetching
│   │
│   └── data/
│       ├── tampa_shelters.json      # Real Tampa Bay shelter locations
│       ├── tampa_zones.json         # Evacuation zones GeoJSON
│       ├── sample_weather.json      # Pre-fetched NOAA data (Hurricane Milton)
│       ├── sample_reports.json      # Simulated field reports for demo
│       └── sample_persons.json      # Simulated missing/found for demo
│
├── supabase/
│   └── migrations/              # Canonical Postgres DDL (applied by init_db)
│       └── *.sql
├── requirements.txt
├── .env.example
├── README.md
└── ARCHITECTURE.md
```

### Agent Details

#### 1. Monitor Agent (Pre-Storm)

```
Purpose: Ingest weather data and calculate neighborhood-level flood risk

Input:
  - NOAA weather data (pre-fetched JSON for demo)
  - USGS water level readings
  - Tampa evacuation zone boundaries
  - Historical flood data for neighborhoods

Processing (via Gemini):
  - Analyze storm trajectory relative to Tampa Bay
  - Calculate flood probability per neighborhood
  - Factor in infrastructure age (South Manhattan Ave, Bayshore Blvd)
  - Determine time-to-impact estimates

Output:
  {
    "neighborhoods": [
      {
        "name": "Palma Ceia",
        "zone": "A",
        "flood_risk": 0.78,
        "storm_surge_ft": 6.2,
        "time_to_impact_hours": 18,
        "recommendation": "evacuate",
        "evacuate_by": "2026-03-28T16:00:00",
        "coordinates": [27.9234, -82.4968]
      },
      {
        "name": "Seminole Heights",
        "zone": "C",
        "flood_risk": 0.42,
        "storm_surge_ft": 2.1,
        "time_to_impact_hours": 22,
        "recommendation": "shelter_in_place",
        "coordinates": [27.9945, -82.4572]
      }
    ],
    "overall_category": "Category 2",
    "landfall_eta": "2026-03-29T02:00:00"
  }
```

#### 2. Alert Agent (Pre-Storm → Active)

```
Purpose: Generate human-readable alerts and deliver via multiple channels

Input:
  - Risk data from Monitor Agent
  - Incident data from Severity Agent (during active phase)
  - User/resident contact preferences

Processing (via Gemini):
  - Convert risk scores into plain-language warnings
  - Personalize by neighborhood
  - Generate multilingual alerts (English, Spanish)
  - Determine alert priority level (info, warning, critical, emergency)

Output:
  {
    "id": "alert-001",
    "phase": "pre_storm",
    "priority": "critical",
    "neighborhood": "Palma Ceia",
    "title": "Evacuation Required — Zone A",
    "message": "Your neighborhood has a 78% flood probability in the next 18 hours. Evacuate via I-275 North by 4:00 PM. Nearest shelter: First Baptist Church of Tampa (2.1 miles).",
    "message_es": "Su vecindario tiene un 78% de probabilidad de inundación...",
    "channels": ["app", "sms", "voice"],
    "created_at": "2026-03-28T10:00:00"
  }

Delivery:
  - App: returned via API to frontend
```

#### 3. Field Report Agent (Active Storm)

```
Purpose: Parse incoming reports from multiple sources into structured incidents

Input:
  - SMS messages (via webhook)
  - App-submitted reports (via frontend form)
  - Raw text in any format, any language

Processing (via Gemini):
  - Extract: location, incident type, severity clues, people count
  - Geocode location from text ("Dale Mabry and Gandy" → lat/lng)
  - Detect language and translate if needed
  - Classify incident type: flooding, structural_damage, trapped_person,
    road_blocked, power_outage, medical_emergency, other

Output:
  {
    "id": "report-001",
    "raw_text": "Water coming into house on Bay to Bay Blvd, 2nd floor with kids",
    "source": "sms",
    "parsed": {
      "location_text": "Bay to Bay Blvd",
      "lat": 27.9120,
      "lng": -82.4930,
      "incident_type": "flooding",
      "people_mentioned": 3,
      "has_children": true,
      "floor_level": 2,
      "language": "en"
    },
    "created_at": "2026-03-29T03:15:00",
    "verified": false,
    "severity_score": null
  }
```

#### 4. Severity Agent (Active Storm)

```
Purpose: Rank verified incidents by urgency and survivability

Input:
  - Structured incidents from Field Report Agent
  - Current resource availability from Resource Agent
  - Weather conditions from Monitor Agent

Processing (via Gemini):
  - Score each incident 0-100 on urgency
  - Factors: life threat, time sensitivity, vulnerable populations (children,
    elderly), water rise rate, rescue accessibility, resource proximity
  - Flag duplicates and consolidate
  - Re-rank as conditions change

Output:
  {
    "id": "incident-001",
    "report_ids": ["report-001", "report-007"],  // consolidated
    "incident_type": "flooding",
    "location": {"lat": 27.9120, "lng": -82.4930, "text": "Bay to Bay Blvd"},
    "severity_score": 92,
    "severity_label": "critical",
    "factors": [
      "children_present",
      "rising_water",
      "second_floor_only"
    ],
    "estimated_response_time_min": 25,
    "recommended_action": "dispatch_water_rescue",
    "verified": true,
    "report_count": 2,
    "last_updated": "2026-03-29T03:20:00"
  }
```

#### 5. Resource Agent (Active → Post-Storm)

```
Purpose: Track all available resources and update database accordingly

Input:
  - Pre-seeded shelter/resource database
  - Real-time updates (capacity changes, road closures)
  - Incident locations from Severity Agent

Resources tracked:
  - Shelters (name, location, capacity, current_occupancy, amenities)
  - Medical facilities (open/closed, specialties)
  - Supply points (water, food, medicine)
  - Charging stations
  - Passable roads / blocked roads
  - Volunteer teams and their locations

Output:
  {
    "id": "resource-001",
    "type": "shelter",
    "name": "First Baptist Church of Tampa",
    "lat": 27.9506,
    "lng": -82.4572,
    "capacity": 200,
    "current_occupancy": 147,
    "available_spots": 53,
    "amenities": ["hot_meals", "medical_station", "pet_friendly", "charging"],
    "status": "open",
    "last_updated": "2026-03-29T08:00:00"
  }

Matching logic:
  - Given an incident location, find nearest resources by type
  - Factor in road accessibility (blocked roads eliminate options)
  - Warn when shelters approach capacity
```

#### 6. Reunification Agent (Post-Storm)

```
Purpose: Match missing person reports against found/shelter data

Input:
  - Missing person reports (from app or SMS)
  - Shelter check-in records
  - "I'm safe" messages
  - Hospital admission data (simulated)

Processing (via Gemini):
  - Fuzzy name matching (spelling variations, nicknames, maiden names)
  - Physical description matching
  - Last known location → likely shelter mapping
  - Age/gender correlation
  - Multilingual name handling

Missing person report:
  {
    "id": "missing-001",
    "reported_by": "Carlos Garcia",
    "name": "Maria Garcia",
    "age": 72,
    "gender": "female",
    "description": "Short gray hair, glasses, uses a walker",
    "last_known_location": "Davis Islands",
    "last_contact": "2026-03-28T18:00:00",
    "phone": "+1813XXXXXXX",
    "status": "missing",
    "created_at": "2026-03-29T06:00:00"
  }

Found/check-in record:
  {
    "id": "found-001",
    "name": "Maria G.",
    "age_approx": 70,
    "gender": "female",
    "description": "Elderly woman with walker, Spanish speaking",
    "found_at": "First Baptist Church shelter",
    "checked_in": "2026-03-29T01:30:00"
  }

Match output:
  {
    "missing_id": "missing-001",
    "found_id": "found-001",
    "confidence": 0.89,
    "match_factors": [
      "name_partial_match: Maria Garcia ↔ Maria G.",
      "age_close: 72 ↔ ~70",
      "gender_match: female",
      "description_match: walker mentioned in both",
      "location_plausible: Davis Islands → First Baptist (2.3 mi)"
    ],
    "status": "pending_confirmation",
    "requires_human_review": true
  }
```

### API Endpoints (Full Contract)

```
BASE URL: http://localhost:8000/api/v1

# ─── Phase Management ───────────────────────────────
GET    /phase                    → { phase: "pre_storm" | "active_storm" | "post_storm", started_at, data }
POST   /phase/advance            → Advance to next phase (operator action)
POST   /phase/set                → Set specific phase { phase: "active_storm" }

# ─── Monitor (Pre-Storm) ────────────────────────────
GET    /monitor/risk             → { neighborhoods: [...risk data] }
GET    /monitor/weather          → { storm data, trajectory, eta }

# ─── Alerts (All Phases) ────────────────────────────
GET    /alerts                   → [{ id, phase, priority, title, message, ... }]
GET    /alerts?priority=critical → Filter by priority
POST   /alerts/generate          → Trigger Alert Agent to generate new alerts

# ─── Field Reports (Active Storm) ───────────────────
GET    /reports                  → [{ id, raw_text, parsed, verified, ... }]
POST   /reports                  → Submit new report { text, source }
POST   /reports/process          → Trigger Field Report Agent on unprocessed reports

# ─── Incidents (Active Storm) ───────────────────────
GET    /incidents                → [{ id, severity_score, location, ... }] sorted by severity
GET    /incidents?severity=critical → Filter by severity label
POST   /incidents/rank           → Trigger Severity Agent to re-rank all incidents

# ─── Resources (Active + Post-Storm) ────────────────
GET    /resources                → [{ id, type, name, lat, lng, status, ... }]
GET    /resources?type=shelter   → Filter by type
GET    /resources/nearest?lat=X&lng=Y&type=shelter → Find nearest resource
PUT    /resources/:id            → Update resource status/capacity

# ─── Reunification (Post-Storm) ─────────────────────
GET    /reunification/missing    → [{ id, name, age, description, status, ... }]
POST   /reunification/missing    → Report missing person
GET    /reunification/found      → [{ id, name, found_at, ... }]
POST   /reunification/found      → Report found person / shelter check-in
GET    /reunification/matches    → [{ missing_id, found_id, confidence, ... }]
POST   /reunification/match      → Trigger Reunification Agent to find matches

# ─── Recovery (Post-Storm) ──────────────────────────
GET    /recovery/briefs          → [{ neighborhood, power, water, roads, shelters, ... }]
GET    /recovery/briefs/:neighborhood → Specific neighborhood brief

# ─── SMS Webhook ──────────────────────────────────────
POST   /sms/webhook              → Receives incoming SMS
```

### Database Schema (PostgreSQL / Supabase)

The backend **does not use SQLite**. All API routes and ADK agents persist through **`app.db.database.get_connection()`**, which opens a **`psycopg`** connection to **PostgreSQL**.

**Canonical DDL** (source of truth for tables, types, and indexes):

- `supabase/migrations/` — SQL migrations; the app runs these via **`init_db()`** in `app/db/database.py` on FastAPI startup (and `python -m app.db.seed` calls `init_db()` before seeding).

**Core tables:** `phase`, `risk_assessments`, `alerts`, `reports`, `incidents`, `resources`, `missing_persons`, `found_persons`, `matches`, `recovery_briefs`, plus **`audit_log`** (agent run audit from several POST routes) and **`assignments`** where defined in migrations.

**Implementation conventions (avoid regressions):**

- **`DATABASE_URL`** must be a Postgres URI (`postgresql://` or `postgres://`), e.g. from Supabase **Settings → Database**.
- Prefer **boolean** columns and SQL literals (`true` / `false` / `TRUE`) consistent with the migration file — not legacy SQLite `0`/`1` integers.
- Use **parameterized queries** (`%s` placeholders) everywhere; never concatenate untrusted input into SQL.
- Optional **`GROQ_API_KEY`**: ADK agents can use LiteLLM with Groq when set; otherwise Gemini (see `.env.example`).

---

## Frontend Architecture (Next.js + Tailwind + React-Leaflet)

### Directory Structure

```
aegis-frontend/
├── src/
│   ├── app/
│   │   ├── layout.tsx           # Root layout with nav + phase indicator
│   │   ├── page.tsx             # Dashboard home (redirects to current phase)
│   │   ├── globals.css          # Tailwind + custom styles
│   │   │
│   │   ├── dashboard/
│   │   │   └── page.tsx         # Main dashboard with map + sidebar
│   │   │
│   │   ├── report/
│   │   │   └── page.tsx         # Submit field report form
│   │   │
│   │   ├── reunify/
│   │   │   └── page.tsx         # Missing/found person portal
│   │   │
│   │   ├── resources/
│   │   │   └── page.tsx         # Resource finder
│   │   │
│   │   └── recovery/
│   │       └── page.tsx         # Neighborhood recovery briefs
│   │
│   ├── components/
│   │   ├── layout/
│   │   │   ├── Navbar.tsx           # Top nav with Aegis logo + phase indicator
│   │   │   ├── PhaseIndicator.tsx   # Shows current phase with progress bar
│   │   │   └── Sidebar.tsx          # Context-sensitive sidebar
│   │   │
│   │   ├── map/
│   │   │   ├── MapContainer.tsx     # Main Leaflet map wrapper
│   │   │   ├── RiskZoneLayer.tsx    # Colored risk zones overlay (pre-storm)
│   │   │   ├── IncidentMarkers.tsx  # Incident pins (active storm)
│   │   │   ├── ResourceMarkers.tsx  # Shelter/supply pins (active + post)
│   │   │   └── MapLegend.tsx        # Color legend for map layers
│   │   │
│   │   ├── alerts/
│   │   │   ├── AlertFeed.tsx        # Scrolling alert list
│   │   │   └── AlertCard.tsx        # Single alert card with priority color
│   │   │
│   │   ├── reports/
│   │   │   ├── ReportForm.tsx       # Submit a field report
│   │   │   └── ReportList.tsx       # List of incoming reports
│   │   │
│   │   ├── incidents/
│   │   │   ├── IncidentList.tsx     # Ranked incident list
│   │   │   └── IncidentCard.tsx     # Single incident with severity badge
│   │   │
│   │   ├── resources/
│   │   │   ├── ResourceList.tsx     # List of resources filtered by type
│   │   │   ├── ResourceCard.tsx     # Single resource with status
│   │   │   └── ResourceFinder.tsx   # "Find nearest" with location input
│   │   │
│   │   ├── reunification/
│   │   │   ├── MissingForm.tsx      # Report missing person
│   │   │   ├── FoundForm.tsx        # Report found person
│   │   │   ├── MatchCard.tsx        # Matched pair with confidence score
│   │   │   └── MatchList.tsx        # All current matches
│   │   │
│   │   ├── recovery/
│   │   │   ├── BriefCard.tsx        # Neighborhood recovery brief
│   │   │   └── BriefList.tsx        # All neighborhood briefs
│   │   │
│   │   └── ui/
│   │       ├── Badge.tsx            # Severity/status badge
│   │       ├── Button.tsx           # Styled button
│   │       ├── Card.tsx             # Base card component
│   │       ├── Input.tsx            # Styled input
│   │       ├── Modal.tsx            # Modal dialog
│   │       └── Tabs.tsx             # Phase tab switcher
│   │
│   ├── lib/
│   │   ├── api.ts               # API client — all fetch calls to backend
│   │   ├── types.ts             # TypeScript types matching backend models
│   │   └── constants.ts         # Tampa Bay coordinates, phase names, colors
│   │
│   └── hooks/
│       ├── usePhase.ts          # Poll current phase from backend
│       ├── useAlerts.ts         # Fetch and auto-refresh alerts
│       ├── useIncidents.ts      # Fetch and auto-refresh incidents
│       └── useResources.ts      # Fetch and auto-refresh resources
│
├── public/
│   ├── aegis-logo.svg           # Logo
│   └── marker-icons/            # Custom map marker icons
│       ├── shelter.png
│       ├── medical.png
│       ├── incident-critical.png
│       ├── incident-high.png
│       └── charging.png
│
├── next.config.js
├── tailwind.config.ts
├── tsconfig.json
├── package.json
└── .env.example                 # NEXT_PUBLIC_API_URL=http://localhost:8000/api/v1
```

### Page Layouts

#### Dashboard (Main Page)

```
┌─────────────────────────────────────────────────────────┐
│  🛡 AEGIS        Dashboard  Report  Reunify  Resources  │
│  ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ │
│  Phase: [PRE-STORM] ──────●─────────────── [POST-STORM] │
├───────────────────────────────────┬─────────────────────┤
│                                   │                     │
│                                   │  ALERT FEED         │
│                                   │  ┌───────────────┐  │
│        TAMPA BAY MAP              │  │ ⚠ CRITICAL    │  │
│        (Leaflet)                  │  │ Evacuate       │  │
│                                   │  │ Palma Ceia     │  │
│        Risk zones shown as        │  │ by 4:00 PM    │  │
│        colored overlays           │  └───────────────┘  │
│                                   │  ┌───────────────┐  │
│        Markers for incidents,     │  │ ⚠ WARNING     │  │
│        shelters, resources        │  │ Flood risk 42% │  │
│                                   │  │ Seminole Hts  │  │
│                                   │  └───────────────┘  │
│                                   │  ┌───────────────┐  │
│                                   │  │ ℹ INFO        │  │
│                                   │  │ Shelter open   │  │
│                                   │  │ First Baptist │  │
│                                   │  └───────────────┘  │
│                                   │                     │
├───────────────────────────────────┴─────────────────────┤
│  INCIDENTS (sorted by severity)                         │
│  ┌────────┐ ┌────────┐ ┌────────┐ ┌────────┐          │
│  │CRIT 92 │ │HIGH 78 │ │HIGH 71 │ │MED  45 │          │
│  │Flooding│ │Power   │ │Road    │ │Tree    │          │
│  │Bay2Bay │ │outage  │ │blocked │ │down    │          │
│  └────────┘ └────────┘ └────────┘ └────────┘          │
└─────────────────────────────────────────────────────────┘
```

#### Reunification Page

```
┌─────────────────────────────────────────────────────────┐
│  🛡 AEGIS        Dashboard  Report  Reunify  Resources  │
├─────────────────────────────┬───────────────────────────┤
│  REPORT MISSING PERSON      │  MATCHES FOUND            │
│  ┌───────────────────────┐  │  ┌─────────────────────┐  │
│  │ Name: ______________ │  │  │ Maria Garcia         │  │
│  │ Age:  ______________ │  │  │ ↔ Maria G.           │  │
│  │ Description: _______ │  │  │ Confidence: 89%      │  │
│  │ Last known: ________ │  │  │ Found at: First      │  │
│  │ [Submit Report]      │  │  │ Baptist Church       │  │
│  └───────────────────────┘  │  │ [Confirm] [Reject]   │  │
│                              │  └─────────────────────┘  │
│  REPORT FOUND PERSON        │  ┌─────────────────────┐  │
│  ┌───────────────────────┐  │  │ James Wilson         │  │
│  │ Name: ______________ │  │  │ ↔ Jim Wilson          │  │
│  │ Found at: _________  │  │  │ Confidence: 94%      │  │
│  │ Description: _______ │  │  │ Found at: USF        │  │
│  │ [Submit Found]       │  │  │ Marshall Center      │  │
│  └───────────────────────┘  │  │ [Confirm] [Reject]   │  │
│                              │  └─────────────────────┘  │
└─────────────────────────────┴───────────────────────────┘
```

### Color System

```
Phase Colors:
  Pre-Storm:    Blue     (#3B82F6)
  Active Storm: Orange   (#F97316)
  Post-Storm:   Green    (#22C55E)

Severity Colors:
  Critical: Red          (#EF4444)
  High:     Orange       (#F97316)
  Medium:   Yellow       (#EAB308)
  Low:      Blue         (#3B82F6)

Resource Status:
  Open:     Green        (#22C55E)
  Limited:  Yellow       (#EAB308)
  Full:     Red          (#EF4444)
  Closed:   Gray         (#6B7280)
```

### TypeScript Types (shared contract)

```typescript
// types.ts — must match backend models exactly

type Phase = "pre_storm" | "active_storm" | "post_storm"
type Priority = "info" | "warning" | "critical" | "emergency"
type SeverityLabel = "low" | "medium" | "high" | "critical"
type IncidentType = "flooding" | "structural_damage" | "trapped_person" |
                    "road_blocked" | "power_outage" | "medical_emergency" | "other"
type ResourceType = "shelter" | "medical" | "supply_point" | "charging" | "road"
type ResourceStatus = "open" | "limited" | "full" | "closed" | "damaged"

interface PhaseState {
  current_phase: Phase
  started_at: string
  updated_at: string
}

interface RiskAssessment {
  neighborhood: string
  zone: string
  lat: number
  lng: number
  flood_risk: number
  storm_surge_ft: number
  time_to_impact_hours: number
  recommendation: "evacuate" | "shelter_in_place" | "monitor"
  evacuate_by: string | null
}

interface Alert {
  id: number
  phase: Phase
  priority: Priority
  neighborhood: string | null
  title: string
  message: string
  message_es: string | null
  channels: string[]
  delivered: boolean
  created_at: string
}

interface Report {
  id: number
  raw_text: string
  source: "sms" | "app" | "partner"
  location_text: string | null
  lat: number | null
  lng: number | null
  incident_type: IncidentType | null
  people_mentioned: number | null
  has_children: boolean
  language: string
  processed: boolean
  created_at: string
}

interface Incident {
  id: number
  report_ids: number[]
  incident_type: IncidentType
  location_text: string
  lat: number
  lng: number
  severity_score: number
  severity_label: SeverityLabel
  factors: string[]
  recommended_action: string
  verified: boolean
  report_count: number
  resolved: boolean
  created_at: string
  updated_at: string
}

interface Resource {
  id: number
  type: ResourceType
  name: string
  lat: number
  lng: number
  address: string | null
  capacity: number | null
  current_occupancy: number | null
  amenities: string[]
  status: ResourceStatus
  notes: string | null
  last_updated: string
}

interface MissingPerson {
  id: number
  reported_by: string
  name: string
  age: number | null
  gender: string | null
  description: string | null
  last_known_location: string | null
  last_known_lat: number | null
  last_known_lng: number | null
  last_contact: string | null
  status: "missing" | "found" | "confirmed_safe"
  created_at: string
}

interface FoundPerson {
  id: number
  name: string
  age_approx: number | null
  gender: string | null
  description: string | null
  found_at: string
  found_lat: number | null
  found_lng: number | null
  checked_in: string
}

interface Match {
  id: number
  missing_id: number
  found_id: number
  confidence: number
  match_factors: string[]
  status: "pending" | "confirmed" | "rejected"
  created_at: string
  missing_person?: MissingPerson
  found_person?: FoundPerson
}

interface RecoveryBrief {
  id: number
  neighborhood: string
  power_status: string
  water_status: string
  roads_status: string
  shelters_nearby: Resource[]
  medical_nearby: Resource[]
  key_updates: string[]
  generated_at: string
}
```

---

## Data Flow Per Phase

### Pre-Storm Flow
```
NOAA/USGS data
    │
    ▼
Monitor Agent ──→ risk_assessments table
    │
    ▼
Alert Agent ──→ alerts table ──→ Frontend alert feed
    ▼
Frontend map shows risk zones colored by flood_risk score
```

### Active Storm Flow
```
SMS webhook ───────────┐
App report form ───────┤
                       ▼
              Field Report Agent ──→ reports table
                       │
                       ▼
              Severity Agent ──→ incidents table
                       │
                       ▼
              Resource Agent ──→ updates resources table
                       │
                       ▼
              Alert Agent ──→ new alerts for critical incidents
                       │
                       ▼
              Frontend shows: incident markers on map +
              ranked incident list + resource status
```

### Post-Storm Flow
```
Missing person form ──→ missing_persons table ──┐
Found person form ────→ found_persons table ────┤
                                                ▼
                                    Reunification Agent
                                          │
                                          ▼
                                    matches table
                                          │
                                          ▼
                        Frontend shows match cards with confidence

Resource Agent continues tracking ──→ updated resource markers
Gemini generates recovery briefs ──→ recovery_briefs table
                                          │
                                          ▼
                        Frontend shows neighborhood brief cards
```

---

## Task Split (4 People)

### Person A: Backend Core + Agents
```
Owns: app/agents/, app/models/, app/db/
Tasks:
  1. FastAPI project setup + CORS + config
  2. PostgreSQL schema (Supabase migrations) + seed data
  3. Google ADK orchestrator setup
  4. Monitor Agent implementation
  5. Alert Agent implementation
  6. Wire agents to API routes
```

### Person B: Backend Reports + Reunification
```
Owns: app/agents/ (field_report, severity, reunification), app/services/
Tasks:
  1. Field Report Agent implementation
  2. Severity Agent implementation
  3. Reunification Agent implementation
  4. Resource Agent implementation
  5. SMS webhook integration
```

### Person C: Frontend Core + Map
```
Owns: src/app/, src/components/map/, src/components/layout/, src/lib/
Tasks:
  1. Next.js project setup + Tailwind config
  2. Layout: Navbar, PhaseIndicator, Sidebar
  3. Leaflet map with Tampa Bay centered
  4. RiskZoneLayer (colored neighborhood overlays)
  5. IncidentMarkers + ResourceMarkers
  6. API client (src/lib/api.ts)
  7. Dashboard page assembly
```

### Person D: Frontend Features + Polish
```
Owns: src/components/alerts, reports, incidents, reunification, resources, recovery
Tasks:
  1. AlertFeed + AlertCard components
  2. ReportForm + ReportList
  3. IncidentList + IncidentCard
  4. Reunification page (MissingForm, FoundForm, MatchCard)
  5. Resource finder page
  6. Recovery brief page
  7. UI polish, logo, responsive design
  8. Demo video recording + Devpost submission
```

### Integration Points (where people must sync)
```
Hour 8:  Person A + B sync → all agents should be callable
Hour 10: Person C + A sync → frontend can call backend API
Hour 14: All sync → end-to-end demo flow works
Hour 18: All sync → polish + demo rehearsal
```

---

## Demo Scenario (seeded data)

The demo tells one story: Hurricane approaching Tampa Bay.

Seeded neighborhoods: Palma Ceia, Davis Islands, Seminole Heights,
  South Tampa, Temple Terrace, Ybor City, Channelside, Hyde Park

Seeded shelters:
  - First Baptist Church of Tampa (27.9506, -82.4572)
  - USF Marshall Center (28.0587, -82.4137)
  - Hillsborough High School (27.9686, -82.4620)
  - Tampa Convention Center (27.9425, -82.4584)

Seeded missing person story:
  - Maria Garcia, 72, Davis Islands → found at First Baptist Church
  - James Wilson, 45, Ybor City → found at USF Marshall Center

Seeded field reports:
  - "Flooding on Bay to Bay Blvd, water entering homes"
  - "Tree down on Dale Mabry blocking both lanes"
  - "Power out in all of Seminole Heights"
  - "Family trapped on second floor, Henderson Blvd"
  - "Hillsborough High shelter needs more water and blankets"
