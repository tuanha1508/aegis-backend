# Aegis Backend

Multi-agent disaster intelligence system for Tampa Bay, powered by Google ADK + FastAPI.

## Agents

- **Monitor Agent** — Ingests NOAA weather, USGS water levels, tide data
- **Alert Agent** — Generates localized warnings via Gemini, SMS (Twilio), voice (ElevenLabs)
- **Field Report Agent** — Processes incoming SMS/text reports during active storm
- **Severity Agent** — Ranks incidents by urgency and survivability
- **Resource Agent** — Tracks shelters, supplies, routes, charging stations
- **Reunification Agent** — Matches missing/found person reports

## Stack

- Python 3.11+
- Google ADK (Agent Development Kit)
- Gemini Flash
- FastAPI
- SQLite
- Twilio (SMS)
- ElevenLabs (voice alerts)

## Setup

```bash
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env  # Add your API keys
uvicorn app.main:app --reload
```

## HackUSF 2026

Built for HackUSF 2026 — "Build with AI" hackathon at University of South Florida.
