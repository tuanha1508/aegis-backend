# Aegis — Multi-Agent Disaster Intelligence Demo

## What You're Looking At

Aegis uses **Google ADK** to orchestrate **6 AI agents** powered by **Gemini** that work together across the full hurricane lifecycle. The graph you see in the ADK Web UI is the **Active Storm Pipeline** — our most complex phase, where agents are composed using ADK's `SequentialAgent` and `ParallelAgent` primitives.

---

## Phase 2: Active Storm (The Demo)

**Pipeline:** `SequentialAgent` → runs three stages in order

**Prompt:** *"Now generate alerts for the highest-priority incidents and summarize them."*

### What happens step by step:

```
┌─────────────────────────────────────────────────────────┐
│            active_storm_pipeline (Sequential)            │
│                                                         │
│  ┌───────────────────┐                                  │
│  │ field_report_agent │ ← Step 1: Parse raw reports     │
│  │  Tools:            │                                  │
│  │  • get_unprocessed_reports()                          │
│  │  • get_tampa_locations()                              │
│  │  • parse_report()                                    │
│  └────────┬──────────┘                                  │
│           ▼                                             │
│  ┌───────────────────┐                                  │
│  │  severity_agent    │ ← Step 2: Score & rank          │
│  │  Tools:            │                                  │
│  │  • get_processed_reports()                            │
│  │  • get_existing_incidents()                           │
│  │  • get_resources()                                   │
│  │  • save_incident()                                   │
│  └────────┬──────────┘                                  │
│           ▼                                             │
│  ┌───────────────────────────────────────┐              │
│  │ active_storm_response (Parallel)      │              │
│  │                                       │              │
│  │  ┌──────────────┐  ┌──────────────┐  │              │
│  │  │ alert_agent   │  │resource_agent│  │              │
│  │  │ • get_risk    │  │• sync        │  │  ← Step 3   │
│  │  │ • get_phase   │  │  resources   │  │  Both run   │
│  │  │ • get_active  │  │              │  │  at once     │
│  │  │   incidents   │  │              │  │              │
│  │  │ • save_alert  │  │              │  │              │
│  │  └──────────────┘  └──────────────┘  │              │
│  └───────────────────────────────────────┘              │
└─────────────────────────────────────────────────────────┘
```

### Stage 1 — Field Report Agent (Steps #2–4 in the UI)

The agent calls `get_unprocessed_reports()` and `get_tampa_locations()` in parallel. It reads raw text reports like:

> *"Family trapped on second floor, Henderson Blvd, 2 adults 2 children"*

Gemini extracts structured fields: location coordinates, incident type (`rescue`), people count (`4`), language (`en`), and geocodes the address against Tampa reference data. Each parsed report is saved back with `processed = true`.

In the demo, all reports were already processed, so it moved on immediately.

### Stage 2 — Severity Agent (Steps #5–9)

Reads all processed reports and scores each by urgency (0–100). Factors include:

| Factor | Weight |
|---|---|
| Life threat (trapped, medical) | Highest |
| Vulnerable people (children, elderly) | High |
| Water rise rate | High |
| Resource proximity (nearest shelter) | Medium |
| Duplicate consolidation | Deduplicates |

Calls `get_processed_reports()`, `get_existing_incidents()`, and `get_resources()` in parallel, then calls `save_incident()` for each ranked incident.

**Demo result — 6 incidents ranked:**

| # | Incident | Severity | Label |
|---|---|---|---|
| 1 | Trapped persons at Henderson Blvd, South Tampa | 95 | Critical |
| 2 | Flooding at Ruskin near Alafia River | 90 | Critical |
| 3 | Structural damage at Hillsborough Ave near 22nd St | 85 | High |
| 4 | Flooding at Bayshore Blvd near Gandy | 80 | High |
| 5 | Medical emergency at Seminole Heights | 70 | Medium |
| 6 | Fire at MacDill AFB area, South Tampa | 60 | Medium |

### Stage 3 — Parallel Response (Steps #10–17)

Two agents run **simultaneously** via ADK `ParallelAgent`:

**Resource Agent** — Scans incident locations and updates shelter/supply point capacity. In the demo, it synced 18 existing resources.

**Alert Agent** — Reads the high-priority incidents, the current phase, and any risk data, then generates plain-language alerts with priority levels. It called `save_alert()` 6 times — one alert per incident.

**Demo result — 6 alerts generated:**

1. Trapped persons in South Tampa → *Deploy rescue teams immediately*
2. Flooding in Ruskin → *Deploy rescue boats immediately*
3. Structural damage at Hillsborough Ave → *Deploy rescue teams and structural engineers*
4. Flooding at Bayshore Blvd → *Deploy rescue teams and sandbags*
5. Medical emergency at Seminole Heights → *Dispatch medical team*
6. Fire in MacDill AFB area → *Dispatch fire department*

---

## Phase 1: Pre-Storm

**Pipeline:** `SequentialAgent` — two agents in sequence

```
monitor_agent  →  alert_agent
```

**What it does:**

1. **Monitor Agent** ingests NOAA weather JSON + Tampa evacuation zone data. Gemini analyzes storm trajectory, wind speed, pressure, surge forecasts, and tidal conditions. It computes a **flood risk score (0–1)** for each of the 8 Tampa Bay neighborhoods and writes them to the database with evacuation recommendations.

2. **Alert Agent** reads the risk assessments and generates **bilingual alerts** (English + Spanish) for neighborhoods with high risk. Priority levels: `info → warning → critical → emergency`. Alerts include evacuation deadlines calculated from time-to-impact minus a 6-hour safety buffer.

**Example output:** *"Zone A neighborhoods Davis Islands and Palma Ceia — evacuate by 6:00 PM. Storm surge estimated at 8–12 feet."*

---

## Phase 3: Post-Storm

**Pipeline:** `ParallelAgent` — two agents run simultaneously

```
reunification_agent  ║  resource_agent
```

**What it does:**

1. **Reunification Agent** pulls all missing person reports and shelter check-in records, then uses Gemini for **fuzzy matching** across 5 dimensions:

   | Dimension | Max Weight |
   |---|---|
   | Name similarity (handles nicknames, abbreviations) | 35% |
   | Physical description overlap | 25% |
   | Age proximity | 15% |
   | Location plausibility | 15% |
   | Gender match | 10% |

   **Demo scenario:** Maria Garcia (72, "short gray hair, glasses, uses a walker", last seen Davis Islands) is matched to "Maria G." (~70, "elderly woman with walker, Spanish speaking", checked in at First Baptist Church) with **~89% confidence**.

2. **Resource Agent** runs in parallel to update shelter capacity, supply levels, and road accessibility as communities begin recovery.

---

## Why This Architecture Matters

- **ADK orchestration, not hardcoded glue** — The `SequentialAgent` and `ParallelAgent` composition means the pipeline order is declarative. Adding a new agent is one line of code.
- **Every agent has real DB tools** — These aren't chat-only agents. Each one reads from and writes to PostgreSQL through function tools that ADK auto-wraps. The data flows through the database, not through prompt chaining.
- **Parallel where possible** — In the active storm phase, alert generation and resource updates happen simultaneously because they don't depend on each other. In post-storm, reunification and resource tracking run at the same time.
- **Gemini does the reasoning** — Risk scoring, severity ranking, fuzzy name matching, and alert wording are all done by Gemini via structured prompts — not hardcoded rules. The agents adapt to novel situations.
- **Full lifecycle coverage** — Pre-storm preparation → active storm triage → post-storm recovery, with the same 6 agents composed differently for each phase.
