import json as _json
import os
from contextlib import asynccontextmanager
from datetime import date, datetime

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse


class _SafeEncoder(_json.JSONEncoder):
    """JSON encoder that handles datetime objects from psycopg."""
    def default(self, obj):
        if isinstance(obj, (datetime, date)):
            return obj.isoformat()
        return super().default(obj)


class SafeJSONResponse(JSONResponse):
    def render(self, content) -> bytes:
        return _json.dumps(content, cls=_SafeEncoder, ensure_ascii=False).encode("utf-8")

from app.api import (
    routes_phase,
    routes_monitor,
    routes_alerts,
    routes_reports,
    routes_incidents,
    routes_resources,
    routes_reunification,
    routes_recovery,
    routes_sms,
    routes_assignments,
    routes_audit,
    routes_live,
    routes_orchestration,
    routes_commander,
)
from app.db.database import init_db


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    # Initialize orchestration_state row
    from app.db.database import get_connection
    conn = get_connection()
    try:
        conn.execute(
            """INSERT INTO orchestration_state (id, operational_mode, scenario_step)
               VALUES (1, 'idle', 'storm_none')
               ON CONFLICT (id) DO NOTHING"""
        )
        conn.commit()
    finally:
        conn.close()

    # Start background scheduler (disable with AUTO_ORCHESTRATE=false)
    if os.getenv("AUTO_ORCHESTRATE", "true").lower() not in ("0", "false", "no"):
        from app.services.orchestration_engine import start_scheduler
        start_scheduler()

    yield

    # Cleanup
    from app.services.orchestration_engine import stop_scheduler
    stop_scheduler()


app = FastAPI(
    title="Aegis",
    description="Multi-agent disaster intelligence for Tampa Bay",
    lifespan=lifespan,
    default_response_class=SafeJSONResponse,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

PREFIX = "/api/v1"
app.include_router(routes_phase.router, prefix=PREFIX)
app.include_router(routes_monitor.router, prefix=PREFIX)
app.include_router(routes_alerts.router, prefix=PREFIX)
app.include_router(routes_reports.router, prefix=PREFIX)
app.include_router(routes_incidents.router, prefix=PREFIX)
app.include_router(routes_resources.router, prefix=PREFIX)
app.include_router(routes_reunification.router, prefix=PREFIX)
app.include_router(routes_recovery.router, prefix=PREFIX)
app.include_router(routes_sms.router, prefix=PREFIX)
app.include_router(routes_assignments.router, prefix=PREFIX)
app.include_router(routes_audit.router, prefix=PREFIX)
app.include_router(routes_live.router, prefix=PREFIX)
app.include_router(routes_orchestration.router, prefix=PREFIX)
app.include_router(routes_commander.router, prefix=PREFIX)


@app.get("/")
async def root():
    return {"name": "Aegis", "status": "operational"}


@app.get("/health")
async def health():
    return {"status": "healthy", "timestamp": datetime.utcnow().isoformat()}


# ─── A2A Agent Discovery ──────────────────────────────────────
# Serves the agent card at the standard well-known path for A2A discovery

@app.get("/.well-known/agent.json")
@app.get("/.well-known/agent-card.json")
async def a2a_agent_card():
    """A2A Agent Card — describes all Aegis specialist agents for discovery."""
    from app.a2a.agent_cards import get_aegis_agent_card
    return get_aegis_agent_card()
