# Aegis Backend

Multi-agent disaster intelligence system for Tampa Bay, powered by Google ADK + FastAPI.

## Agents

- **Monitor Agent** — Ingests NOAA weather, USGS water levels, tide data
- **Alert Agent** — Generates localized warnings via Gemini
- **Field Report Agent** — Processes incoming SMS/text reports during active storm
- **Severity Agent** — Ranks incidents by urgency and survivability
- **Resource Agent** — Tracks shelters, supplies, routes, charging stations
- **Reunification Agent** — Matches missing/found person reports

## Stack

- Python 3.11+
- Google ADK (Agent Development Kit)
- Gemini Flash (optional: Groq via LiteLLM when `GROQ_API_KEY` is set)
- FastAPI
- **PostgreSQL** (hosted on **Supabase** in production; connection via `DATABASE_URL`)

## Database

Persistent data lives in **Postgres**, not SQLite. Configure `DATABASE_URL` with a `postgresql://` or `postgres://` URI (see Supabase **Settings → Database**). Schema is defined under `supabase/migrations/`; `app.main` runs `init_db()` on startup to apply migrations. For local demo data, run `python -m app.db.seed` after `.env` is configured.

## Setup

```bash
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env  # Add API keys and DATABASE_URL (Supabase Postgres)
python -m app.db.seed   # optional: load Tampa Bay demo rows
uvicorn app.main:app --reload
```

## HackUSF 2026

Built for HackUSF 2026 — "Build with AI" hackathon at University of South Florida.
