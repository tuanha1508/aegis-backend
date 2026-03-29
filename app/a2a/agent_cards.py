"""
A2A Agent Cards — Defines each Aegis agent's identity and skills
for the Agent-to-Agent discovery protocol.

Each agent exposes an agent card at /.well-known/agent-card.json
so other agents (or the orchestrator) can discover and call them.
"""

from __future__ import annotations

import os

# Base URL for agent endpoints — set via env or default to localhost
A2A_BASE_URL = os.getenv("A2A_BASE_URL", "http://localhost:8000")


def get_aegis_agent_card() -> dict:
    """Return the master Aegis agent card describing all specialist agents.

    This is served at /.well-known/agent.json for A2A discovery.
    """
    return {
        "name": "Aegis Disaster Intelligence",
        "description": (
            "Multi-agent disaster response system for Tampa Bay. "
            "Coordinates 6 specialist agents across the full storm lifecycle: "
            "pre-storm monitoring, active storm response, and post-storm recovery."
        ),
        "url": A2A_BASE_URL,
        "version": "1.0.0",
        "protocolVersion": "0.2.6",
        "provider": {
            "organization": "Team Aegis — HackUSF 2026",
            "url": "https://github.com/tuanha1508/aegis-backend",
        },
        "capabilities": {
            "streaming": False,
            "pushNotifications": False,
        },
        "defaultInputModes": ["text/plain", "application/json"],
        "defaultOutputModes": ["application/json"],
        "supportsAuthenticatedExtendedCard": False,
        "skills": [
            {
                "id": "aegis-monitor",
                "name": "Monitor Agent",
                "description": (
                    "Analyzes NOAA weather data and Tampa Bay evacuation zones "
                    "to produce per-neighborhood flood risk scores (0-1), storm "
                    "surge estimates, and evacuation recommendations."
                ),
                "tags": ["weather", "risk-assessment", "flood", "hurricane", "noaa", "gemini"],
                "examples": [
                    "Analyze storm data and compute risk for all Tampa Bay neighborhoods",
                    "What is the flood risk for Davis Islands?",
                ],
                "inputModes": ["text/plain"],
                "outputModes": ["application/json"],
            },
            {
                "id": "aegis-alert",
                "name": "Alert Agent",
                "description": (
                    "Generates multilingual (EN/ES) disaster alerts based on "
                    "risk assessments and active incidents. Determines priority "
                    "(info/warning/critical/emergency) and delivery channels."
                ),
                "tags": ["alerts", "notifications", "multilingual", "emergency", "gemini"],
                "examples": [
                    "Generate evacuation alerts for high-risk neighborhoods",
                    "Create emergency alert for trapped persons incident",
                ],
                "inputModes": ["text/plain"],
                "outputModes": ["application/json"],
            },
            {
                "id": "aegis-field-report",
                "name": "Field Report Agent",
                "description": (
                    "Parses raw disaster reports (SMS, app submissions) into "
                    "structured data: extracts location, geocodes using Tampa "
                    "reference data, classifies incident type, detects language, "
                    "and counts people mentioned."
                ),
                "tags": ["nlp", "geocoding", "classification", "sms", "reports", "gemini"],
                "examples": [
                    "Parse: 'Flooding on Bayshore Blvd, water entering homes'",
                    "Parse: 'Familia atrapada en el segundo piso, Henderson Blvd'",
                ],
                "inputModes": ["text/plain"],
                "outputModes": ["application/json"],
            },
            {
                "id": "aegis-severity",
                "name": "Severity Agent",
                "description": (
                    "Scores disaster incidents by urgency (0-100), consolidates "
                    "duplicate reports, considers life threat, vulnerable populations, "
                    "resource proximity, and recommends emergency response actions."
                ),
                "tags": ["triage", "severity", "scoring", "incidents", "gemini"],
                "examples": [
                    "Score and rank all processed field reports by urgency",
                    "Consolidate duplicate flooding reports for South Tampa",
                ],
                "inputModes": ["text/plain"],
                "outputModes": ["application/json"],
            },
            {
                "id": "aegis-resource",
                "name": "Resource Agent",
                "description": (
                    "Tracks shelter capacity, finds nearest resources (shelters, "
                    "medical, fire stations) using Haversine distance, monitors "
                    "demand from active incidents, and recommends deployments."
                ),
                "tags": ["resources", "shelters", "logistics", "geospatial", "gemini"],
                "examples": [
                    "Find nearest open shelter to Davis Islands",
                    "Update shelter capacity and recommend overflow options",
                ],
                "inputModes": ["text/plain"],
                "outputModes": ["application/json"],
            },
            {
                "id": "aegis-reunification",
                "name": "Reunification Agent",
                "description": (
                    "Matches missing persons with found/shelter check-in records "
                    "using fuzzy name matching, age/gender/description comparison, "
                    "and location plausibility analysis. Returns confidence scores."
                ),
                "tags": ["reunification", "missing-persons", "matching", "fuzzy-search", "gemini"],
                "examples": [
                    "Match missing person Maria Garcia (72, walker) with found records",
                    "Find potential matches for all missing persons",
                ],
                "inputModes": ["text/plain"],
                "outputModes": ["application/json"],
            },
            {
                "id": "aegis-orchestrator",
                "name": "Orchestrator",
                "description": (
                    "Coordinates all specialist agents using ADK SequentialAgent "
                    "and ParallelAgent based on the current disaster phase. "
                    "Pre-storm: Monitor→Alert. Active: FieldReport→Severity→"
                    "[Resource+Alert]. Post: [Reunification+Resource]."
                ),
                "tags": ["orchestration", "pipeline", "parallel", "sequential", "adk"],
                "examples": [
                    "Run the full pre-storm analysis pipeline",
                    "Execute active storm response pipeline",
                ],
                "inputModes": ["text/plain"],
                "outputModes": ["application/json"],
            },
            {
                "id": "aegis-commander",
                "name": "Situation Commander",
                "description": (
                    "Central intelligence coordinator that accepts natural language "
                    "questions and delegates to all specialist agents. Returns "
                    "synthesized situational awareness reports."
                ),
                "tags": ["commander", "nlp", "synthesis", "a2a", "delegation"],
                "examples": [
                    "What's the current situation in Tampa Bay?",
                    "Is Davis Islands safe right now?",
                    "Has Maria Garcia been found?",
                    "Where can people go for shelter?",
                    "What should we do next?",
                ],
                "inputModes": ["text/plain"],
                "outputModes": ["application/json"],
            },
            {
                "id": "aegis-verification",
                "name": "Verification LoopAgent",
                "description": (
                    "Self-correcting LoopAgent that iteratively reviews severity "
                    "scores, identifies scoring errors, and re-scores incidents. "
                    "Demonstrates autonomous self-correction capability."
                ),
                "tags": ["verification", "loop-agent", "self-correction", "quality-control"],
                "examples": [
                    "Review and verify all incident severity scores",
                    "Self-correct any mis-scored incidents",
                ],
                "inputModes": ["text/plain"],
                "outputModes": ["application/json"],
            },
        ],
        "supportedInterfaces": [
            {
                "url": f"{A2A_BASE_URL}/api/v1",
                "protocolBinding": "JSONRPC",
                "protocolVersion": "0.2.6",
            }
        ],
    }
