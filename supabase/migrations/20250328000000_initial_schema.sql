-- Aegis initial schema (Postgres / Supabase). Apply via Supabase SQL editor or CLI, or via app init_db.

CREATE EXTENSION IF NOT EXISTS pgcrypto;

CREATE TABLE IF NOT EXISTS phase (
    id INTEGER PRIMARY KEY DEFAULT 1 CHECK (id = 1),
    current_phase TEXT NOT NULL DEFAULT 'pre_storm',
    started_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS risk_assessments (
    id BIGSERIAL PRIMARY KEY,
    neighborhood TEXT NOT NULL,
    zone TEXT,
    lat DOUBLE PRECISION NOT NULL,
    lng DOUBLE PRECISION NOT NULL,
    flood_risk DOUBLE PRECISION,
    storm_surge_ft DOUBLE PRECISION,
    time_to_impact_hours DOUBLE PRECISION,
    recommendation TEXT,
    evacuate_by TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS alerts (
    id BIGSERIAL PRIMARY KEY,
    phase TEXT NOT NULL,
    priority TEXT NOT NULL,
    neighborhood TEXT,
    title TEXT NOT NULL,
    message TEXT NOT NULL,
    message_es TEXT,
    channels TEXT,
    delivered BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS reports (
    id BIGSERIAL PRIMARY KEY,
    raw_text TEXT NOT NULL,
    source TEXT NOT NULL,
    sender_phone TEXT,
    location_text TEXT,
    lat DOUBLE PRECISION,
    lng DOUBLE PRECISION,
    incident_type TEXT,
    people_mentioned INTEGER,
    has_children BOOLEAN DEFAULT FALSE,
    language TEXT DEFAULT 'en',
    processed BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS incidents (
    id BIGSERIAL PRIMARY KEY,
    report_ids TEXT,
    incident_type TEXT NOT NULL,
    location_text TEXT,
    lat DOUBLE PRECISION NOT NULL,
    lng DOUBLE PRECISION NOT NULL,
    severity_score INTEGER,
    severity_label TEXT,
    factors TEXT,
    recommended_action TEXT,
    verified BOOLEAN DEFAULT FALSE,
    report_count INTEGER DEFAULT 1,
    resolved BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS resources (
    id BIGSERIAL PRIMARY KEY,
    type TEXT NOT NULL,
    name TEXT NOT NULL,
    lat DOUBLE PRECISION NOT NULL,
    lng DOUBLE PRECISION NOT NULL,
    address TEXT,
    capacity INTEGER,
    current_occupancy INTEGER DEFAULT 0,
    amenities TEXT,
    status TEXT DEFAULT 'open',
    notes TEXT,
    last_updated TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS missing_persons (
    id BIGSERIAL PRIMARY KEY,
    reported_by TEXT NOT NULL,
    reporter_phone TEXT,
    name TEXT NOT NULL,
    age INTEGER,
    gender TEXT,
    description TEXT,
    last_known_location TEXT,
    last_known_lat DOUBLE PRECISION,
    last_known_lng DOUBLE PRECISION,
    last_contact TIMESTAMPTZ,
    status TEXT DEFAULT 'missing',
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS found_persons (
    id BIGSERIAL PRIMARY KEY,
    name TEXT NOT NULL,
    age_approx INTEGER,
    gender TEXT,
    description TEXT,
    found_at TEXT,
    found_lat DOUBLE PRECISION,
    found_lng DOUBLE PRECISION,
    checked_in TIMESTAMPTZ DEFAULT NOW(),
    matched_missing_id BIGINT REFERENCES missing_persons (id)
);

CREATE TABLE IF NOT EXISTS matches (
    id BIGSERIAL PRIMARY KEY,
    missing_id BIGINT NOT NULL REFERENCES missing_persons (id),
    found_id BIGINT NOT NULL REFERENCES found_persons (id),
    confidence DOUBLE PRECISION NOT NULL,
    match_factors TEXT,
    status TEXT DEFAULT 'pending',
    reviewed_by TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS recovery_briefs (
    id BIGSERIAL PRIMARY KEY,
    neighborhood TEXT NOT NULL,
    power_status TEXT,
    water_status TEXT,
    roads_status TEXT,
    shelters_nearby TEXT,
    medical_nearby TEXT,
    key_updates TEXT,
    generated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS assignments (
    id BIGSERIAL PRIMARY KEY,
    incident_id BIGINT NOT NULL REFERENCES incidents (id) ON DELETE CASCADE,
    recommended_action TEXT,
    assignee TEXT,
    status TEXT NOT NULL DEFAULT 'pending',
    assigned_at TIMESTAMPTZ DEFAULT NOW(),
    accepted_at TIMESTAMPTZ,
    completed_at TIMESTAMPTZ,
    notes TEXT
);

CREATE TABLE IF NOT EXISTS audit_log (
    id BIGSERIAL PRIMARY KEY,
    agent_name TEXT NOT NULL,
    run_id UUID DEFAULT gen_random_uuid(),
    phase TEXT,
    input_payload JSONB,
    output_payload JSONB,
    error_message TEXT,
    duration_ms INTEGER,
    related_report_id BIGINT REFERENCES reports (id) ON DELETE SET NULL,
    related_incident_id BIGINT REFERENCES incidents (id) ON DELETE SET NULL,
    related_assignment_id BIGINT REFERENCES assignments (id) ON DELETE SET NULL,
    created_at TIMESTAMPTZ DEFAULT NOW()
);
