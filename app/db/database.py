import sqlite3
from pathlib import Path

DB_PATH = Path("aegis.db")

SCHEMA = """
CREATE TABLE IF NOT EXISTS phase (
    id INTEGER PRIMARY KEY DEFAULT 1,
    current_phase TEXT NOT NULL DEFAULT 'pre_storm',
    started_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS risk_assessments (
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

CREATE TABLE IF NOT EXISTS alerts (
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

CREATE TABLE IF NOT EXISTS reports (
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

CREATE TABLE IF NOT EXISTS incidents (
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

CREATE TABLE IF NOT EXISTS resources (
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

CREATE TABLE IF NOT EXISTS missing_persons (
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

CREATE TABLE IF NOT EXISTS found_persons (
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

CREATE TABLE IF NOT EXISTS matches (
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

CREATE TABLE IF NOT EXISTS recovery_briefs (
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
"""


def get_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def init_db():
    conn = get_connection()
    conn.executescript(SCHEMA)
    cursor = conn.execute("SELECT COUNT(*) FROM phase")
    if cursor.fetchone()[0] == 0:
        conn.execute("INSERT INTO phase (id, current_phase) VALUES (1, 'pre_storm')")
    conn.commit()
    conn.close()
