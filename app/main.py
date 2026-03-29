from contextlib import asynccontextmanager
from datetime import datetime

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

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
)
from app.db.database import init_db


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    yield


app = FastAPI(
    title="Aegis",
    description="Multi-agent disaster intelligence for Tampa Bay",
    lifespan=lifespan,
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


@app.get("/")
async def root():
    return {"name": "Aegis", "status": "operational"}


@app.get("/health")
async def health():
    return {"status": "healthy", "timestamp": datetime.utcnow().isoformat()}
