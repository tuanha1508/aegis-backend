import json
from pathlib import Path

from app.db.database import get_connection, init_db

DATA_DIR = Path(__file__).parent.parent / "data"


def seed():
    init_db()
    conn = get_connection()

    # Clear existing seed data
    for table in [
        "recovery_briefs",
        "matches",
        "found_persons",
        "missing_persons",
        "incidents",
        "alerts",
        "reports",
        "resources",
        "risk_assessments",
    ]:
        conn.execute(f"DELETE FROM {table}")

    # Seed risk assessments from zones
    with open(DATA_DIR / "tampa_zones.json") as f:
        zones = json.load(f)
    for z in zones:
        conn.execute(
            """INSERT INTO risk_assessments
               (neighborhood, zone, lat, lng, flood_risk, storm_surge_ft,
                time_to_impact_hours, recommendation)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                z["neighborhood"],
                z["zone"],
                z["lat"],
                z["lng"],
                z["flood_risk"],
                z["storm_surge_ft"],
                z["time_to_impact_hours"],
                z["recommendation"],
            ),
        )

    # Seed shelters
    with open(DATA_DIR / "tampa_shelters.json") as f:
        shelters = json.load(f)
    for s in shelters:
        conn.execute(
            """INSERT INTO resources
               (type, name, lat, lng, address, capacity, amenities, status)
               VALUES (?, ?, ?, ?, ?, ?, ?, 'open')""",
            (
                s["type"],
                s["name"],
                s["lat"],
                s["lng"],
                s.get("address"),
                s["capacity"],
                s["amenities"],
            ),
        )

    # Seed sample reports (pre-processed)
    with open(DATA_DIR / "sample_reports.json") as f:
        reports = json.load(f)
    for r in reports:
        conn.execute(
            """INSERT INTO reports
               (raw_text, source, sender_phone, location_text, lat, lng,
                incident_type, people_mentioned, has_children, language, processed)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1)""",
            (
                r["raw_text"],
                r["source"],
                r.get("sender_phone"),
                r["location_text"],
                r["lat"],
                r["lng"],
                r["incident_type"],
                r.get("people_mentioned"),
                1 if r.get("has_children") else 0,
                r["language"],
            ),
        )

    # Seed missing persons
    with open(DATA_DIR / "sample_persons.json") as f:
        persons = json.load(f)
    for m in persons["missing"]:
        conn.execute(
            """INSERT INTO missing_persons
               (reported_by, reporter_phone, name, age, gender, description,
                last_known_location, last_known_lat, last_known_lng, last_contact)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                m["reported_by"],
                m.get("reporter_phone"),
                m["name"],
                m["age"],
                m["gender"],
                m["description"],
                m["last_known_location"],
                m["last_known_lat"],
                m["last_known_lng"],
                m.get("last_contact"),
            ),
        )
    for fp in persons["found"]:
        conn.execute(
            """INSERT INTO found_persons
               (name, age_approx, gender, description, found_at, found_lat, found_lng)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (
                fp["name"],
                fp.get("age_approx"),
                fp.get("gender"),
                fp["description"],
                fp["found_at"],
                fp.get("found_lat"),
                fp.get("found_lng"),
            ),
        )

    conn.commit()
    conn.close()
    print("Seed complete — Tampa Bay demo data loaded.")


if __name__ == "__main__":
    seed()
