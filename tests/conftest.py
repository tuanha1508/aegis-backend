"""Pytest fixtures for FastAPI TestClient and seeded Postgres state."""

from __future__ import annotations

import os

# Before importing the app: disable background scheduler during tests
os.environ["AUTO_ORCHESTRATE"] = "false"

import pytest
from fastapi.testclient import TestClient

from app.db.seed import clear_demo_tables, seed


@pytest.fixture
def client() -> TestClient:
    """API client against migrations + empty demo tables (no seed JSON)."""
    clear_demo_tables()
    from app.main import app

    with TestClient(app) as c:
        yield c


@pytest.fixture
def seeded_client() -> TestClient:
    """API client after full Tampa seed (shelters, zones, reports, persons, …)."""
    from app.main import app

    seed()
    with TestClient(app) as c:
        yield c
