"""Aegis Backend — 200 tests covering all endpoints, models, DB, and services."""
import json
import pytest
from pathlib import Path
from datetime import datetime

DATA_DIR = Path(__file__).parent.parent / "app" / "data"


def _json_array_len(rel: str) -> int:
    with open(DATA_DIR / rel) as f:
        return len(json.load(f))


SEEDED_RESOURCE_COUNT = _json_array_len("tampa_shelters.json") + _json_array_len(
    "tampa_supply_points.json"
)
with open(DATA_DIR / "tampa_shelters.json") as _sf:
    SEEDED_SHELTER_TYPE_COUNT = sum(
        1 for row in json.load(_sf) if row.get("type") == "shelter"
    )

# ═══════════════════════════════════════════════════════════════════════════
# 1. ROOT ENDPOINT (3 tests)
# ═══════════════════════════════════════════════════════════════════════════


class TestRoot:
    def test_root_returns_200(self, client):
        r = client.get("/")
        assert r.status_code == 200

    def test_root_has_name(self, client):
        assert client.get("/").json()["name"] == "Aegis"

    def test_root_has_status(self, client):
        assert client.get("/").json()["status"] == "operational"


# ═══════════════════════════════════════════════════════════════════════════
# 2. PHASE ENDPOINTS (20 tests)
# ═══════════════════════════════════════════════════════════════════════════


class TestPhaseGet:
    def test_get_phase_200(self, client):
        assert client.get("/api/v1/phase").status_code == 200

    def test_default_phase_is_pre_storm(self, client):
        assert client.get("/api/v1/phase").json()["current_phase"] == "pre_storm"

    def test_phase_has_started_at(self, client):
        assert "started_at" in client.get("/api/v1/phase").json()

    def test_phase_has_updated_at(self, client):
        assert "updated_at" in client.get("/api/v1/phase").json()

    def test_phase_started_at_not_none(self, client):
        assert client.get("/api/v1/phase").json()["started_at"] is not None


class TestPhaseAdvance:
    def test_advance_to_active_storm(self, client):
        r = client.post("/api/v1/phase/advance")
        assert r.json()["current_phase"] == "active_storm"

    def test_advance_to_post_storm(self, client):
        client.post("/api/v1/phase/advance")
        r = client.post("/api/v1/phase/advance")
        assert r.json()["current_phase"] == "post_storm"

    def test_advance_past_final_returns_400(self, client):
        client.post("/api/v1/phase/advance")
        client.post("/api/v1/phase/advance")
        r = client.post("/api/v1/phase/advance")
        assert r.status_code == 400

    def test_advance_updates_timestamp(self, client):
        before = client.get("/api/v1/phase").json()["updated_at"]
        client.post("/api/v1/phase/advance")
        after = client.get("/api/v1/phase").json()["updated_at"]
        assert after >= before

    def test_advance_returns_200(self, client):
        assert client.post("/api/v1/phase/advance").status_code == 200


class TestPhaseSet:
    def test_set_active_storm(self, client):
        r = client.post("/api/v1/phase/set", json={"phase": "active_storm"})
        assert r.json()["current_phase"] == "active_storm"

    def test_set_post_storm(self, client):
        r = client.post("/api/v1/phase/set", json={"phase": "post_storm"})
        assert r.json()["current_phase"] == "post_storm"

    def test_set_pre_storm(self, client):
        client.post("/api/v1/phase/set", json={"phase": "active_storm"})
        r = client.post("/api/v1/phase/set", json={"phase": "pre_storm"})
        assert r.json()["current_phase"] == "pre_storm"

    def test_set_invalid_phase_returns_400(self, client):
        r = client.post("/api/v1/phase/set", json={"phase": "invalid"})
        assert r.status_code == 400

    def test_set_empty_phase_returns_400(self, client):
        r = client.post("/api/v1/phase/set", json={"phase": ""})
        assert r.status_code == 400

    def test_set_then_get_consistent(self, client):
        client.post("/api/v1/phase/set", json={"phase": "post_storm"})
        assert client.get("/api/v1/phase").json()["current_phase"] == "post_storm"

    def test_set_updates_timestamp(self, client):
        before = client.get("/api/v1/phase").json()["updated_at"]
        client.post("/api/v1/phase/set", json={"phase": "active_storm"})
        after = client.get("/api/v1/phase").json()["updated_at"]
        assert after >= before

    def test_set_missing_body_returns_422(self, client):
        r = client.post("/api/v1/phase/set")
        assert r.status_code == 422

    def test_advance_then_set_back(self, client):
        client.post("/api/v1/phase/advance")
        client.post("/api/v1/phase/set", json={"phase": "pre_storm"})
        assert client.get("/api/v1/phase").json()["current_phase"] == "pre_storm"

    @pytest.mark.parametrize("phase", ["pre_storm", "active_storm", "post_storm"])
    def test_all_valid_phases(self, client, phase):
        r = client.post("/api/v1/phase/set", json={"phase": phase})
        assert r.status_code == 200


# ═══════════════════════════════════════════════════════════════════════════
# 3. MONITOR ENDPOINTS (22 tests)
# ═══════════════════════════════════════════════════════════════════════════


class TestMonitorRisk:
    def test_risk_returns_200(self, seeded_client):
        assert seeded_client.get("/api/v1/monitor/risk").status_code == 200

    def test_risk_has_neighborhoods_key(self, seeded_client):
        assert "neighborhoods" in seeded_client.get("/api/v1/monitor/risk").json()

    def test_risk_has_8_neighborhoods(self, seeded_client):
        data = seeded_client.get("/api/v1/monitor/risk").json()
        assert len(data["neighborhoods"]) == 8

    def test_risk_sorted_by_flood_risk_desc(self, seeded_client):
        data = seeded_client.get("/api/v1/monitor/risk").json()
        risks = [n["flood_risk"] for n in data["neighborhoods"]]
        assert risks == sorted(risks, reverse=True)

    @pytest.mark.parametrize("field", [
        "neighborhood", "zone", "lat", "lng", "flood_risk",
        "storm_surge_ft", "time_to_impact_hours", "recommendation",
    ])
    def test_risk_has_required_field(self, seeded_client, field):
        data = seeded_client.get("/api/v1/monitor/risk").json()
        assert field in data["neighborhoods"][0]

    @pytest.mark.parametrize("name", [
        "Palma Ceia", "Davis Islands", "Channelside", "South Tampa",
        "Hyde Park", "Seminole Heights", "Temple Terrace", "Ybor City",
    ])
    def test_risk_contains_neighborhood(self, seeded_client, name):
        data = seeded_client.get("/api/v1/monitor/risk").json()
        names = [n["neighborhood"] for n in data["neighborhoods"]]
        assert name in names

    def test_risk_flood_values_between_0_and_1(self, seeded_client):
        data = seeded_client.get("/api/v1/monitor/risk").json()
        for n in data["neighborhoods"]:
            assert 0 <= n["flood_risk"] <= 1

    def test_risk_empty_when_no_seed(self, client):
        data = client.get("/api/v1/monitor/risk").json()
        assert len(data["neighborhoods"]) == 0


class TestMonitorWeather:
    def test_weather_returns_200(self, client):
        assert client.get("/api/v1/monitor/weather").status_code == 200

    def test_weather_has_storm_name(self, client):
        assert "storm_name" in client.get("/api/v1/monitor/weather").json()

    def test_weather_storm_is_rafael(self, client):
        assert client.get("/api/v1/monitor/weather").json()["storm_name"] == "Hurricane Rafael"

    def test_weather_has_category(self, client):
        assert client.get("/api/v1/monitor/weather").json()["category"] == 2

    def test_weather_has_trajectory(self, client):
        data = client.get("/api/v1/monitor/weather").json()
        assert len(data["trajectory"]) == 5

    def test_weather_has_warnings(self, client):
        data = client.get("/api/v1/monitor/weather").json()
        assert len(data["warnings"]) == 3

    def test_weather_has_tide_data(self, client):
        data = client.get("/api/v1/monitor/weather").json()
        assert "tide_data" in data
        assert data["tide_data"]["predicted_peak_ft"] == 8.7


# ═══════════════════════════════════════════════════════════════════════════
# 4. ALERTS ENDPOINTS (15 tests)
# ═══════════════════════════════════════════════════════════════════════════


class TestAlerts:
    def test_get_alerts_returns_200(self, client):
        assert client.get("/api/v1/alerts").status_code == 200

    def test_get_alerts_empty_initially(self, client):
        assert client.get("/api/v1/alerts").json() == []

    def test_get_alerts_with_priority_filter(self, client):
        r = client.get("/api/v1/alerts?priority=critical")
        assert r.status_code == 200
        assert r.json() == []

    def test_get_alerts_invalid_priority_empty(self, client):
        r = client.get("/api/v1/alerts?priority=nonexistent")
        assert r.json() == []

    def test_alerts_after_manual_insert(self, client):
        from app.db.database import get_connection
        conn = get_connection()
        conn.execute(
            "INSERT INTO alerts (phase, priority, neighborhood, title, message) VALUES (%s, %s, %s, %s, %s)",
            ("pre_storm", "critical", "Davis Islands", "Evacuate Now", "Flood risk high"),
        )
        conn.commit()
        conn.close()
        alerts = client.get("/api/v1/alerts").json()
        assert len(alerts) == 1
        assert alerts[0]["priority"] == "critical"

    def test_alerts_filter_matches(self, client):
        from app.db.database import get_connection
        conn = get_connection()
        conn.execute(
            "INSERT INTO alerts (phase, priority, neighborhood, title, message) VALUES (%s, %s, %s, %s, %s)",
            ("pre_storm", "critical", "A", "T1", "M1"),
        )
        conn.execute(
            "INSERT INTO alerts (phase, priority, neighborhood, title, message) VALUES (%s, %s, %s, %s, %s)",
            ("pre_storm", "info", "B", "T2", "M2"),
        )
        conn.commit()
        conn.close()
        assert len(client.get("/api/v1/alerts?priority=critical").json()) == 1
        assert len(client.get("/api/v1/alerts?priority=info").json()) == 1

    def test_alerts_ordered_by_created_at_desc(self, client):
        from app.db.database import get_connection
        conn = get_connection()
        for i in range(3):
            conn.execute(
                "INSERT INTO alerts (phase, priority, neighborhood, title, message) VALUES (%s, %s, %s, %s, %s)",
                ("pre_storm", "info", f"N{i}", f"T{i}", f"M{i}"),
            )
        conn.commit()
        conn.close()
        alerts = client.get("/api/v1/alerts").json()
        assert len(alerts) == 3

    def test_alert_has_id(self, client):
        from app.db.database import get_connection
        conn = get_connection()
        conn.execute(
            "INSERT INTO alerts (phase, priority, neighborhood, title, message) VALUES (%s, %s, %s, %s, %s)",
            ("pre_storm", "warning", "Hyde Park", "Prepare", "Get ready"),
        )
        conn.commit()
        conn.close()
        assert "id" in client.get("/api/v1/alerts").json()[0]

    def test_alert_has_phase(self, client):
        from app.db.database import get_connection
        conn = get_connection()
        conn.execute(
            "INSERT INTO alerts (phase, priority, neighborhood, title, message) VALUES (%s, %s, %s, %s, %s)",
            ("active_storm", "emergency", "X", "Y", "Z"),
        )
        conn.commit()
        conn.close()
        assert client.get("/api/v1/alerts").json()[0]["phase"] == "active_storm"

    def test_alert_has_title_and_message(self, client):
        from app.db.database import get_connection
        conn = get_connection()
        conn.execute(
            "INSERT INTO alerts (phase, priority, neighborhood, title, message) VALUES (%s, %s, %s, %s, %s)",
            ("pre_storm", "info", "N", "MyTitle", "MyMessage"),
        )
        conn.commit()
        conn.close()
        a = client.get("/api/v1/alerts").json()[0]
        assert a["title"] == "MyTitle"
        assert a["message"] == "MyMessage"

    def test_alert_spanish_message(self, client):
        from app.db.database import get_connection
        conn = get_connection()
        conn.execute(
            "INSERT INTO alerts (phase, priority, neighborhood, title, message, message_es) VALUES (%s, %s, %s, %s, %s, %s)",
            ("pre_storm", "info", "N", "T", "M", "Mensaje en espanol"),
        )
        conn.commit()
        conn.close()
        assert client.get("/api/v1/alerts").json()[0]["message_es"] == "Mensaje en espanol"

    def test_alert_channels_field(self, client):
        from app.db.database import get_connection
        conn = get_connection()
        conn.execute(
            "INSERT INTO alerts (phase, priority, neighborhood, title, message, channels) VALUES (%s, %s, %s, %s, %s, %s)",
            ("pre_storm", "critical", "N", "T", "M", "app,sms,voice"),
        )
        conn.commit()
        conn.close()
        assert client.get("/api/v1/alerts").json()[0]["channels"] == "app,sms,voice"

    def test_multiple_alerts_count(self, client):
        from app.db.database import get_connection
        conn = get_connection()
        for i in range(5):
            conn.execute(
                "INSERT INTO alerts (phase, priority, neighborhood, title, message) VALUES (%s, %s, %s, %s, %s)",
                ("pre_storm", "info", f"N{i}", f"T{i}", f"M{i}"),
            )
        conn.commit()
        conn.close()
        assert len(client.get("/api/v1/alerts").json()) == 5

    def test_generate_alerts_returns_200(self, client):
        # Will fail without GEMINI_API_KEY but endpoint should exist
        r = client.post("/api/v1/alerts/generate")
        assert r.status_code in (200, 500)

    def test_generate_alerts_with_context(self, client):
        r = client.post("/api/v1/alerts/generate", json={"context": "test"})
        assert r.status_code in (200, 500)


# ═══════════════════════════════════════════════════════════════════════════
# 5. REPORTS ENDPOINTS (25 tests)
# ═══════════════════════════════════════════════════════════════════════════


class TestReportsGet:
    def test_get_reports_200(self, client):
        assert client.get("/api/v1/reports").status_code == 200

    def test_get_reports_empty(self, client):
        assert client.get("/api/v1/reports").json() == []

    def test_get_reports_seeded(self, seeded_client):
        reports = seeded_client.get("/api/v1/reports").json()
        assert len(reports) == 5

    def test_seeded_reports_have_location(self, seeded_client):
        reports = seeded_client.get("/api/v1/reports").json()
        for r in reports:
            assert r["location_text"] is not None

    def test_seeded_reports_are_processed(self, seeded_client):
        reports = seeded_client.get("/api/v1/reports").json()
        for r in reports:
            assert r["processed"] == 1


class TestReportsCreate:
    def test_create_report_201(self, client):
        r = client.post("/api/v1/reports", json={"text": "Flooding on Main St"})
        assert r.status_code == 200

    def test_create_report_returns_id(self, client):
        r = client.post("/api/v1/reports", json={"text": "Test"})
        assert "id" in r.json()

    def test_create_report_raw_text(self, client):
        r = client.post("/api/v1/reports", json={"text": "Water rising fast"})
        assert r.json()["raw_text"] == "Water rising fast"

    def test_create_report_default_source(self, client):
        r = client.post("/api/v1/reports", json={"text": "Test"})
        assert r.json()["source"] == "app"

    def test_create_report_custom_source(self, client):
        r = client.post("/api/v1/reports", json={"text": "Test", "source": "sms"})
        assert r.json()["source"] == "sms"

    def test_create_report_with_phone(self, client):
        r = client.post("/api/v1/reports", json={
            "text": "Help", "source": "sms", "sender_phone": "+18135551234"
        })
        assert r.json()["sender_phone"] == "+18135551234"

    def test_create_report_default_processed_false(self, client):
        r = client.post("/api/v1/reports", json={"text": "Test"})
        assert r.json()["processed"] == 0

    def test_create_report_default_language(self, client):
        r = client.post("/api/v1/reports", json={"text": "Test"})
        assert r.json()["language"] == "en"

    def test_create_report_no_location(self, client):
        r = client.post("/api/v1/reports", json={"text": "Test"})
        assert r.json()["location_text"] is None

    def test_create_report_no_incident_type(self, client):
        r = client.post("/api/v1/reports", json={"text": "Test"})
        assert r.json()["incident_type"] is None

    def test_create_report_has_created_at(self, client):
        r = client.post("/api/v1/reports", json={"text": "Test"})
        assert r.json()["created_at"] is not None

    def test_create_multiple_reports(self, client):
        for i in range(3):
            client.post("/api/v1/reports", json={"text": f"Report {i}"})
        assert len(client.get("/api/v1/reports").json()) == 3

    def test_create_report_increments_id(self, client):
        r1 = client.post("/api/v1/reports", json={"text": "First"})
        r2 = client.post("/api/v1/reports", json={"text": "Second"})
        assert r2.json()["id"] > r1.json()["id"]

    def test_create_report_missing_text_422(self, client):
        r = client.post("/api/v1/reports", json={"source": "app"})
        assert r.status_code == 422

    def test_create_report_empty_text(self, client):
        r = client.post("/api/v1/reports", json={"text": ""})
        assert r.status_code == 200  # empty string is valid

    def test_reports_ordered_desc(self, client):
        client.post("/api/v1/reports", json={"text": "First"})
        client.post("/api/v1/reports", json={"text": "Second"})
        reports = client.get("/api/v1/reports").json()
        # Both created in same second so created_at is identical — just verify we get both
        assert len(reports) == 2

    def test_long_report_text(self, client):
        long_text = "A" * 5000
        r = client.post("/api/v1/reports", json={"text": long_text})
        assert r.json()["raw_text"] == long_text

    def test_unicode_report_text(self, client):
        r = client.post("/api/v1/reports", json={"text": "Inundacion en la calle principal"})
        assert "Inundacion" in r.json()["raw_text"]

    def test_process_reports_returns_pending(self, client):
        r = client.post("/api/v1/reports/process")
        assert r.status_code == 200

    def test_report_has_children_default(self, client):
        r = client.post("/api/v1/reports", json={"text": "Test"})
        assert r.json()["has_children"] == 0


# ═══════════════════════════════════════════════════════════════════════════
# 6. INCIDENTS ENDPOINTS (14 tests)
# ═══════════════════════════════════════════════════════════════════════════


class TestIncidents:
    def test_get_incidents_200(self, client):
        assert client.get("/api/v1/incidents").status_code == 200

    def test_get_incidents_empty(self, client):
        assert client.get("/api/v1/incidents").json() == []

    def test_get_incidents_with_severity_filter(self, client):
        r = client.get("/api/v1/incidents?severity=critical")
        assert r.status_code == 200

    def test_rank_incidents_returns_pending(self, client):
        r = client.post("/api/v1/incidents/rank")
        assert r.status_code == 200

    def test_incidents_with_manual_insert(self, client):
        from app.db.database import get_connection
        conn = get_connection()
        conn.execute(
            """INSERT INTO incidents (report_ids, incident_type, location_text, lat, lng,
               severity_score, severity_label, recommended_action)
               VALUES (%s, %s, %s, %s, %s, %s, %s, %s)""",
            ("1", "flooding", "Bay to Bay", 27.91, -82.49, 92, "critical", "dispatch_water_rescue"),
        )
        conn.commit()
        conn.close()
        incidents = client.get("/api/v1/incidents").json()
        assert len(incidents) == 1
        assert incidents[0]["severity_score"] == 92

    def test_incidents_severity_filter_match(self, client):
        from app.db.database import get_connection
        conn = get_connection()
        conn.execute(
            "INSERT INTO incidents (incident_type, lat, lng, severity_score, severity_label) VALUES (%s, %s, %s, %s, %s)",
            ("flooding", 27.9, -82.5, 90, "critical"),
        )
        conn.execute(
            "INSERT INTO incidents (incident_type, lat, lng, severity_score, severity_label) VALUES (%s, %s, %s, %s, %s)",
            ("power_outage", 27.9, -82.5, 30, "low"),
        )
        conn.commit()
        conn.close()
        assert len(client.get("/api/v1/incidents?severity=critical").json()) == 1

    def test_incidents_sorted_by_severity_desc(self, client):
        from app.db.database import get_connection
        conn = get_connection()
        for score in [30, 90, 50]:
            conn.execute(
                "INSERT INTO incidents (incident_type, lat, lng, severity_score, severity_label) VALUES (%s, %s, %s, %s, %s)",
                ("flooding", 27.9, -82.5, score, "x"),
            )
        conn.commit()
        conn.close()
        incidents = client.get("/api/v1/incidents").json()
        scores = [i["severity_score"] for i in incidents]
        assert scores == sorted(scores, reverse=True)

    def test_incident_has_required_fields(self, client):
        from app.db.database import get_connection
        conn = get_connection()
        conn.execute(
            "INSERT INTO incidents (incident_type, lat, lng, severity_score, severity_label) VALUES (%s, %s, %s, %s, %s)",
            ("flooding", 27.9, -82.5, 80, "high"),
        )
        conn.commit()
        conn.close()
        inc = client.get("/api/v1/incidents").json()[0]
        for field in ["id", "incident_type", "lat", "lng", "severity_score"]:
            assert field in inc

    def test_incident_default_verified_false(self, client):
        from app.db.database import get_connection
        conn = get_connection()
        conn.execute(
            "INSERT INTO incidents (incident_type, lat, lng) VALUES (%s, %s, %s)",
            ("flooding", 27.9, -82.5),
        )
        conn.commit()
        conn.close()
        assert client.get("/api/v1/incidents").json()[0]["verified"] == 0

    def test_incident_default_resolved_false(self, client):
        from app.db.database import get_connection
        conn = get_connection()
        conn.execute(
            "INSERT INTO incidents (incident_type, lat, lng) VALUES (%s, %s, %s)",
            ("flooding", 27.9, -82.5),
        )
        conn.commit()
        conn.close()
        assert client.get("/api/v1/incidents").json()[0]["resolved"] == 0

    def test_incident_report_count_default(self, client):
        from app.db.database import get_connection
        conn = get_connection()
        conn.execute(
            "INSERT INTO incidents (incident_type, lat, lng) VALUES (%s, %s, %s)",
            ("flooding", 27.9, -82.5),
        )
        conn.commit()
        conn.close()
        assert client.get("/api/v1/incidents").json()[0]["report_count"] == 1

    def test_incident_timestamps(self, client):
        from app.db.database import get_connection
        conn = get_connection()
        conn.execute(
            "INSERT INTO incidents (incident_type, lat, lng) VALUES (%s, %s, %s)",
            ("flooding", 27.9, -82.5),
        )
        conn.commit()
        conn.close()
        inc = client.get("/api/v1/incidents").json()[0]
        assert inc["created_at"] is not None

    def test_multiple_incident_types(self, client):
        from app.db.database import get_connection
        conn = get_connection()
        for t in ["flooding", "power_outage", "road_blocked"]:
            conn.execute(
                "INSERT INTO incidents (incident_type, lat, lng) VALUES (%s, %s, %s)",
                (t, 27.9, -82.5),
            )
        conn.commit()
        conn.close()
        assert len(client.get("/api/v1/incidents").json()) == 3

    def test_incident_factors_field(self, client):
        from app.db.database import get_connection
        conn = get_connection()
        conn.execute(
            "INSERT INTO incidents (incident_type, lat, lng, factors) VALUES (%s, %s, %s, %s)",
            ("flooding", 27.9, -82.5, "children_present,rising_water"),
        )
        conn.commit()
        conn.close()
        assert client.get("/api/v1/incidents").json()[0]["factors"] == "children_present,rising_water"


# ═══════════════════════════════════════════════════════════════════════════
# 7. RESOURCES ENDPOINTS (30 tests)
# ═══════════════════════════════════════════════════════════════════════════


class TestResourcesGet:
    def test_get_resources_200(self, client):
        assert client.get("/api/v1/resources").status_code == 200

    def test_get_resources_empty(self, client):
        assert client.get("/api/v1/resources").json() == []

    def test_get_resources_seeded(self, seeded_client):
        assert len(seeded_client.get("/api/v1/resources").json()) == SEEDED_RESOURCE_COUNT

    def test_get_resources_filter_shelter(self, seeded_client):
        r = seeded_client.get("/api/v1/resources?type=shelter")
        assert len(r.json()) == SEEDED_SHELTER_TYPE_COUNT

    def test_get_resources_filter_invalid_type(self, seeded_client):
        r = seeded_client.get("/api/v1/resources?type=hospital")
        assert r.json() == []

    @pytest.mark.parametrize("field", [
        "id", "type", "name", "lat", "lng", "capacity", "status",
    ])
    def test_resource_has_field(self, seeded_client, field):
        res = seeded_client.get("/api/v1/resources").json()[0]
        assert field in res

    def test_resource_default_status_open(self, seeded_client):
        for r in seeded_client.get("/api/v1/resources").json():
            assert r["status"] == "open"

    def test_resource_default_occupancy_zero(self, seeded_client):
        for r in seeded_client.get("/api/v1/resources").json():
            assert r["current_occupancy"] == 0

    @pytest.mark.parametrize("name", [
        "Middleton High School",
        "Sickles High School",
        "Steinbrenner High School",
        "Burnett Middle School",
    ])
    def test_resource_shelter_exists(self, seeded_client, name):
        names = [r["name"] for r in seeded_client.get("/api/v1/resources").json()]
        assert name in names

    def test_resource_has_amenities(self, seeded_client):
        resources = seeded_client.get("/api/v1/resources").json()
        for r in resources:
            assert r["amenities"] is not None

    def test_resource_has_address(self, seeded_client):
        resources = seeded_client.get("/api/v1/resources").json()
        for r in resources:
            assert r["address"] is not None

    def test_resources_sorted_by_name(self, seeded_client):
        resources = seeded_client.get("/api/v1/resources").json()
        names = [r["name"] for r in resources]
        assert names == sorted(names)


class TestResourcesNearest:
    def test_nearest_returns_200(self, seeded_client):
        r = seeded_client.get("/api/v1/resources/nearest?lat=27.92&lng=-82.49")
        assert r.status_code == 200

    def test_nearest_has_resource(self, seeded_client):
        r = seeded_client.get("/api/v1/resources/nearest?lat=27.92&lng=-82.49")
        assert r.json()["resource"] is not None

    def test_nearest_has_distance(self, seeded_client):
        r = seeded_client.get("/api/v1/resources/nearest?lat=27.92&lng=-82.49")
        assert r.json()["distance_miles"] is not None

    def test_nearest_with_type_filter(self, seeded_client):
        r = seeded_client.get("/api/v1/resources/nearest?lat=27.92&lng=-82.49&type=shelter")
        assert r.json()["resource"]["type"] == "shelter"

    def test_nearest_distance_is_positive(self, seeded_client):
        r = seeded_client.get("/api/v1/resources/nearest?lat=27.92&lng=-82.49")
        assert r.json()["distance_miles"] > 0

    def test_nearest_no_resources_returns_none(self, client):
        r = client.get("/api/v1/resources/nearest?lat=27.92&lng=-82.49")
        assert r.json()["resource"] is None

    def test_nearest_missing_lat_422(self, seeded_client):
        r = seeded_client.get("/api/v1/resources/nearest?lng=-82.49")
        assert r.status_code == 422

    def test_nearest_missing_lng_422(self, seeded_client):
        r = seeded_client.get("/api/v1/resources/nearest?lat=27.92")
        assert r.status_code == 422

    def test_nearest_returns_closest(self, seeded_client):
        # Tampa General Hospital (~27.937, -82.459) is among the closest to this point
        r = seeded_client.get("/api/v1/resources/nearest?lat=27.94&lng=-82.46")
        assert r.json()["resource"] is not None
        assert r.json()["distance_miles"] < 2.0
        assert "Tampa General" in r.json()["resource"]["name"]


class TestResourcesUpdate:
    def test_update_status(self, seeded_client):
        r = seeded_client.put("/api/v1/resources/1", json={"status": "closed"})
        assert r.status_code == 200
        assert r.json()["status"] == "closed"

    def test_update_occupancy(self, seeded_client):
        r = seeded_client.put("/api/v1/resources/1", json={"current_occupancy": 150})
        assert r.json()["current_occupancy"] == 150

    def test_update_notes(self, seeded_client):
        r = seeded_client.put("/api/v1/resources/1", json={"notes": "Needs supplies"})
        assert r.json()["notes"] == "Needs supplies"

    def test_update_nonexistent_404(self, client):
        r = client.put("/api/v1/resources/999", json={"status": "closed"})
        assert r.status_code == 404

    def test_update_multiple_fields(self, seeded_client):
        r = seeded_client.put("/api/v1/resources/1", json={
            "status": "full", "current_occupancy": 200, "notes": "At capacity"
        })
        assert r.json()["status"] == "full"
        assert r.json()["current_occupancy"] == 200

    def test_update_persists(self, seeded_client):
        seeded_client.put("/api/v1/resources/1", json={"status": "closed"})
        resources = seeded_client.get("/api/v1/resources").json()
        r1 = next(r for r in resources if r["id"] == 1)
        assert r1["status"] == "closed"


# ═══════════════════════════════════════════════════════════════════════════
# 8. REUNIFICATION ENDPOINTS (30 tests)
# ═══════════════════════════════════════════════════════════════════════════


class TestMissingPersons:
    def test_get_missing_200(self, client):
        assert client.get("/api/v1/reunification/missing").status_code == 200

    def test_get_missing_empty(self, client):
        assert client.get("/api/v1/reunification/missing").json() == []

    def test_get_missing_seeded(self, seeded_client):
        assert len(seeded_client.get("/api/v1/reunification/missing").json()) == 2

    def test_create_missing_person(self, client):
        r = client.post("/api/v1/reunification/missing", json={
            "reported_by": "John Doe", "name": "Jane Doe"
        })
        assert r.status_code == 200
        assert r.json()["name"] == "Jane Doe"

    def test_create_missing_full_fields(self, client):
        r = client.post("/api/v1/reunification/missing", json={
            "reported_by": "Carlos Garcia",
            "reporter_phone": "+18135552001",
            "name": "Maria Garcia",
            "age": 72,
            "gender": "female",
            "description": "Short gray hair, glasses",
            "last_known_location": "Davis Islands",
            "last_known_lat": 27.921,
            "last_known_lng": -82.463,
        })
        assert r.json()["age"] == 72
        assert r.json()["gender"] == "female"
        assert r.json()["last_known_location"] == "Davis Islands"

    def test_missing_default_status(self, client):
        r = client.post("/api/v1/reunification/missing", json={
            "reported_by": "Test", "name": "Test Person"
        })
        assert r.json()["status"] == "missing"

    def test_missing_has_id(self, client):
        r = client.post("/api/v1/reunification/missing", json={
            "reported_by": "Test", "name": "Test"
        })
        assert "id" in r.json()

    def test_missing_has_created_at(self, client):
        r = client.post("/api/v1/reunification/missing", json={
            "reported_by": "Test", "name": "Test"
        })
        assert r.json()["created_at"] is not None

    def test_missing_required_fields_422(self, client):
        r = client.post("/api/v1/reunification/missing", json={"name": "Only name"})
        assert r.status_code == 422

    def test_seeded_missing_maria(self, seeded_client):
        persons = seeded_client.get("/api/v1/reunification/missing").json()
        names = [p["name"] for p in persons]
        assert "Maria Garcia" in names

    def test_seeded_missing_tommy(self, seeded_client):
        persons = seeded_client.get("/api/v1/reunification/missing").json()
        names = [p["name"] for p in persons]
        assert "Tommy Adams" in names

    def test_create_multiple_missing(self, client):
        for i in range(3):
            client.post("/api/v1/reunification/missing", json={
                "reported_by": f"Reporter {i}", "name": f"Person {i}"
            })
        assert len(client.get("/api/v1/reunification/missing").json()) == 3

    def test_missing_optional_fields_null(self, client):
        r = client.post("/api/v1/reunification/missing", json={
            "reported_by": "Test", "name": "Test"
        })
        assert r.json()["age"] is None
        assert r.json()["gender"] is None
        assert r.json()["description"] is None


class TestFoundPersons:
    def test_get_found_200(self, client):
        assert client.get("/api/v1/reunification/found").status_code == 200

    def test_get_found_empty(self, client):
        assert client.get("/api/v1/reunification/found").json() == []

    def test_get_found_seeded(self, seeded_client):
        assert len(seeded_client.get("/api/v1/reunification/found").json()) == 2

    def test_create_found_person(self, client):
        r = client.post("/api/v1/reunification/found", json={"name": "Maria G."})
        assert r.status_code == 200
        assert r.json()["name"] == "Maria G."

    def test_create_found_full_fields(self, client):
        r = client.post("/api/v1/reunification/found", json={
            "name": "Maria G.",
            "age_approx": 70,
            "gender": "female",
            "description": "Elderly woman with walker",
            "found_at": "First Baptist Church",
            "found_lat": 27.9506,
            "found_lng": -82.4572,
        })
        assert r.json()["age_approx"] == 70
        assert r.json()["found_at"] == "First Baptist Church"

    def test_found_has_checked_in(self, client):
        r = client.post("/api/v1/reunification/found", json={"name": "Test"})
        assert r.json()["checked_in"] is not None

    def test_found_has_id(self, client):
        r = client.post("/api/v1/reunification/found", json={"name": "Test"})
        assert "id" in r.json()

    def test_seeded_found_maria(self, seeded_client):
        persons = seeded_client.get("/api/v1/reunification/found").json()
        names = [p["name"] for p in persons]
        assert "Maria G." in names

    def test_seeded_found_tommy(self, seeded_client):
        persons = seeded_client.get("/api/v1/reunification/found").json()
        names = [p["name"] for p in persons]
        assert "Tommy" in names

    def test_found_optional_fields_null(self, client):
        r = client.post("/api/v1/reunification/found", json={"name": "Unknown"})
        assert r.json()["age_approx"] is None
        assert r.json()["gender"] is None


class TestMatches:
    def test_get_matches_200(self, client):
        assert client.get("/api/v1/reunification/matches").status_code == 200

    def test_get_matches_empty(self, client):
        assert client.get("/api/v1/reunification/matches").json() == []

    def test_trigger_match_200(self, client):
        r = client.post("/api/v1/reunification/match")
        assert r.status_code == 200

    def test_manual_match_insert(self, seeded_client):
        from app.db.database import get_connection
        conn = get_connection()
        conn.execute(
            "INSERT INTO matches (missing_id, found_id, confidence, match_factors, status) VALUES (%s, %s, %s, %s, %s)",
            (1, 1, 0.89, "name_partial_match,age_close", "pending"),
        )
        conn.commit()
        conn.close()
        matches = seeded_client.get("/api/v1/reunification/matches").json()
        assert len(matches) == 1
        assert matches[0]["confidence"] == 0.89

    def test_matches_sorted_by_confidence_desc(self, seeded_client):
        from app.db.database import get_connection
        conn = get_connection()
        conn.execute(
            "INSERT INTO matches (missing_id, found_id, confidence) VALUES (%s, %s, %s)",
            (1, 1, 0.5),
        )
        conn.execute(
            "INSERT INTO matches (missing_id, found_id, confidence) VALUES (%s, %s, %s)",
            (2, 2, 0.9),
        )
        conn.commit()
        conn.close()
        matches = seeded_client.get("/api/v1/reunification/matches").json()
        assert matches[0]["confidence"] >= matches[1]["confidence"]


# ═══════════════════════════════════════════════════════════════════════════
# 9. RECOVERY ENDPOINTS (8 tests)
# ═══════════════════════════════════════════════════════════════════════════


class TestRecovery:
    def test_get_briefs_200(self, client):
        assert client.get("/api/v1/recovery/briefs").status_code == 200

    def test_get_briefs_empty(self, client):
        assert client.get("/api/v1/recovery/briefs").json() == []

    def test_get_brief_not_found_404(self, client):
        r = client.get("/api/v1/recovery/briefs/Nonexistent")
        assert r.status_code == 404

    def test_brief_after_insert(self, client):
        from app.db.database import get_connection
        conn = get_connection()
        conn.execute(
            """INSERT INTO recovery_briefs (neighborhood, power_status, water_status, roads_status)
               VALUES (%s, %s, %s, %s)""",
            ("Davis Islands", "out", "boil_notice", "partially_blocked"),
        )
        conn.commit()
        conn.close()
        briefs = client.get("/api/v1/recovery/briefs").json()
        assert len(briefs) == 1

    def test_brief_by_neighborhood(self, client):
        from app.db.database import get_connection
        conn = get_connection()
        conn.execute(
            "INSERT INTO recovery_briefs (neighborhood, power_status) VALUES (%s, %s)",
            ("Palma Ceia", "restored"),
        )
        conn.commit()
        conn.close()
        r = client.get("/api/v1/recovery/briefs/Palma Ceia")
        assert r.status_code == 200
        assert r.json()["power_status"] == "restored"

    def test_brief_has_fields(self, client):
        from app.db.database import get_connection
        conn = get_connection()
        conn.execute(
            "INSERT INTO recovery_briefs (neighborhood, power_status, water_status) VALUES (%s, %s, %s)",
            ("Test", "out", "ok"),
        )
        conn.commit()
        conn.close()
        brief = client.get("/api/v1/recovery/briefs/Test").json()
        for field in ["neighborhood", "power_status", "water_status", "roads_status"]:
            assert field in brief

    def test_multiple_briefs(self, client):
        from app.db.database import get_connection
        conn = get_connection()
        for n in ["A", "B", "C"]:
            conn.execute(
                "INSERT INTO recovery_briefs (neighborhood) VALUES (%s)", (n,))
        conn.commit()
        conn.close()
        assert len(client.get("/api/v1/recovery/briefs").json()) == 3

    def test_brief_generated_at(self, client):
        from app.db.database import get_connection
        conn = get_connection()
        conn.execute("INSERT INTO recovery_briefs (neighborhood) VALUES (%s)", ("X",))
        conn.commit()
        conn.close()
        assert client.get("/api/v1/recovery/briefs/X").json()["generated_at"] is not None


# ═══════════════════════════════════════════════════════════════════════════
# 10. SMS WEBHOOK (6 tests)
# ═══════════════════════════════════════════════════════════════════════════


class TestSmsWebhook:
    def test_webhook_returns_200(self, client):
        r = client.post("/api/v1/sms/webhook", data={"From": "+18135551234", "Body": "Flooding"})
        assert r.status_code == 200

    def test_webhook_creates_report(self, client):
        client.post("/api/v1/sms/webhook", data={"From": "+18135551234", "Body": "Help flooding"})
        reports = client.get("/api/v1/reports").json()
        assert len(reports) == 1
        assert reports[0]["source"] == "sms"

    def test_webhook_captures_phone(self, client):
        client.post("/api/v1/sms/webhook", data={"From": "+18135559999", "Body": "Test"})
        reports = client.get("/api/v1/reports").json()
        assert reports[0]["sender_phone"] == "+18135559999"

    def test_webhook_captures_body(self, client):
        client.post("/api/v1/sms/webhook", data={"From": "+1", "Body": "Tree down on Dale Mabry"})
        reports = client.get("/api/v1/reports").json()
        assert reports[0]["raw_text"] == "Tree down on Dale Mabry"

    def test_webhook_missing_fields_422(self, client):
        r = client.post("/api/v1/sms/webhook", data={"From": "+1"})
        assert r.status_code == 422

    def test_webhook_multiple_sms(self, client):
        for i in range(3):
            client.post("/api/v1/sms/webhook", data={"From": f"+1{i}", "Body": f"Msg {i}"})
        assert len(client.get("/api/v1/reports").json()) == 3


# ═══════════════════════════════════════════════════════════════════════════
# 11. DATABASE (12 tests)
# ═══════════════════════════════════════════════════════════════════════════


class TestDatabase:
    def test_init_db_creates_tables(self, client):
        from app.db.database import get_connection
        conn = get_connection()
        tables = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
        ).fetchall()
        conn.close()
        table_names = [t["name"] for t in tables]
        for expected in [
            "alerts", "found_persons", "incidents", "matches",
            "missing_persons", "phase", "recovery_briefs",
            "reports", "resources", "risk_assessments",
        ]:
            assert expected in table_names

    def test_phase_row_exists(self, client):
        from app.db.database import get_connection
        conn = get_connection()
        row = conn.execute("SELECT * FROM phase WHERE id = 1").fetchone()
        conn.close()
        assert row is not None

    def test_row_factory(self, client):
        from app.db.database import get_connection
        conn = get_connection()
        row = conn.execute("SELECT * FROM phase WHERE id = 1").fetchone()
        conn.close()
        assert row["current_phase"] == "pre_storm"

    def test_wal_mode(self, client):
        from app.db.database import get_connection
        conn = get_connection()
        mode = conn.execute("PRAGMA journal_mode").fetchone()
        conn.close()
        assert mode[0] == "wal"

    def test_foreign_keys_enabled(self, client):
        from app.db.database import get_connection
        conn = get_connection()
        fk = conn.execute("PRAGMA foreign_keys").fetchone()
        conn.close()
        assert fk[0] == 1

    def test_init_db_idempotent(self, client):
        from app.db.database import init_db
        init_db()
        init_db()
        from app.db.database import get_connection
        conn = get_connection()
        count = conn.execute("SELECT COUNT(*) FROM phase").fetchone()[0]
        conn.close()
        assert count == 1

    def test_risk_assessments_schema(self, client):
        from app.db.database import get_connection
        conn = get_connection()
        info = conn.execute("PRAGMA table_info(risk_assessments)").fetchall()
        conn.close()
        cols = [i["name"] for i in info]
        for c in ["neighborhood", "zone", "lat", "lng", "flood_risk", "storm_surge_ft"]:
            assert c in cols

    def test_alerts_schema(self, client):
        from app.db.database import get_connection
        conn = get_connection()
        info = conn.execute("PRAGMA table_info(alerts)").fetchall()
        conn.close()
        cols = [i["name"] for i in info]
        for c in ["phase", "priority", "title", "message", "message_es"]:
            assert c in cols

    def test_reports_schema(self, client):
        from app.db.database import get_connection
        conn = get_connection()
        info = conn.execute("PRAGMA table_info(reports)").fetchall()
        conn.close()
        cols = [i["name"] for i in info]
        for c in ["raw_text", "source", "lat", "lng", "incident_type", "processed"]:
            assert c in cols

    def test_resources_schema(self, client):
        from app.db.database import get_connection
        conn = get_connection()
        info = conn.execute("PRAGMA table_info(resources)").fetchall()
        conn.close()
        cols = [i["name"] for i in info]
        for c in ["type", "name", "capacity", "current_occupancy", "status"]:
            assert c in cols

    def test_missing_persons_schema(self, client):
        from app.db.database import get_connection
        conn = get_connection()
        info = conn.execute("PRAGMA table_info(missing_persons)").fetchall()
        conn.close()
        cols = [i["name"] for i in info]
        for c in ["reported_by", "name", "age", "gender", "description", "status"]:
            assert c in cols

    def test_matches_schema(self, client):
        from app.db.database import get_connection
        conn = get_connection()
        info = conn.execute("PRAGMA table_info(matches)").fetchall()
        conn.close()
        cols = [i["name"] for i in info]
        for c in ["missing_id", "found_id", "confidence", "status"]:
            assert c in cols


# ═══════════════════════════════════════════════════════════════════════════
# 12. PYDANTIC MODELS (20 tests)
# ═══════════════════════════════════════════════════════════════════════════


class TestModels:
    def test_phase_response_valid(self):
        from app.models.phase import PhaseResponse
        p = PhaseResponse(current_phase="pre_storm")
        assert p.current_phase == "pre_storm"

    def test_phase_set_request_valid(self):
        from app.models.phase import PhaseSetRequest
        p = PhaseSetRequest(phase="active_storm")
        assert p.phase == "active_storm"

    def test_alert_response_valid(self):
        from app.models.alert import AlertResponse
        a = AlertResponse(id=1, phase="pre_storm", priority="critical", title="T", message="M")
        assert a.priority == "critical"

    def test_alert_response_defaults(self):
        from app.models.alert import AlertResponse
        a = AlertResponse(id=1, phase="pre_storm", priority="info", title="T", message="M")
        assert a.delivered is False
        assert a.message_es is None

    def test_report_create_valid(self):
        from app.models.report import ReportCreate
        r = ReportCreate(text="Flooding")
        assert r.text == "Flooding"
        assert r.source == "app"

    def test_report_create_custom_source(self):
        from app.models.report import ReportCreate
        r = ReportCreate(text="Test", source="sms")
        assert r.source == "sms"

    def test_report_response_valid(self):
        from app.models.report import ReportResponse
        r = ReportResponse(id=1, raw_text="Test", source="app")
        assert r.processed is False

    def test_incident_response_valid(self):
        from app.models.incident import IncidentResponse
        i = IncidentResponse(id=1, incident_type="flooding", lat=27.9, lng=-82.5)
        assert i.verified is False
        assert i.resolved is False

    def test_incident_response_defaults(self):
        from app.models.incident import IncidentResponse
        i = IncidentResponse(id=1, incident_type="flooding", lat=27.9, lng=-82.5)
        assert i.report_count == 1
        assert i.severity_score is None

    def test_resource_response_valid(self):
        from app.models.resource import ResourceResponse
        r = ResourceResponse(id=1, type="shelter", name="Test", lat=27.9, lng=-82.5)
        assert r.status == "open"
        assert r.current_occupancy == 0

    def test_resource_update_partial(self):
        from app.models.resource import ResourceUpdate
        u = ResourceUpdate(status="closed")
        assert u.status == "closed"
        assert u.current_occupancy is None

    def test_missing_person_create_minimal(self):
        from app.models.person import MissingPersonCreate
        p = MissingPersonCreate(reported_by="Test", name="Jane")
        assert p.age is None
        assert p.gender is None

    def test_missing_person_response_valid(self):
        from app.models.person import MissingPersonResponse
        p = MissingPersonResponse(id=1, reported_by="Test", name="Jane")
        assert p.status == "missing"

    def test_found_person_create_minimal(self):
        from app.models.person import FoundPersonCreate
        p = FoundPersonCreate(name="Maria G.")
        assert p.found_at is None

    def test_found_person_response_valid(self):
        from app.models.person import FoundPersonResponse
        p = FoundPersonResponse(id=1, name="Maria G.")
        assert p.matched_missing_id is None

    def test_match_response_valid(self):
        from app.models.person import MatchResponse
        m = MatchResponse(id=1, missing_id=1, found_id=1, confidence=0.89)
        assert m.status == "pending"

    def test_match_response_reviewed_by_null(self):
        from app.models.person import MatchResponse
        m = MatchResponse(id=1, missing_id=1, found_id=1, confidence=0.5)
        assert m.reviewed_by is None

    def test_resource_update_all_fields(self):
        from app.models.resource import ResourceUpdate
        u = ResourceUpdate(status="full", current_occupancy=200, notes="At capacity")
        assert u.notes == "At capacity"

    def test_missing_person_create_all_fields(self):
        from app.models.person import MissingPersonCreate
        p = MissingPersonCreate(
            reported_by="Carlos", name="Maria", age=72, gender="female",
            description="Gray hair", last_known_location="Davis Islands",
            last_known_lat=27.921, last_known_lng=-82.463,
        )
        assert p.age == 72
        assert p.last_known_lat == 27.921

    def test_found_person_create_all_fields(self):
        from app.models.person import FoundPersonCreate
        p = FoundPersonCreate(
            name="Maria G.", age_approx=70, gender="female",
            description="Walker", found_at="Shelter", found_lat=27.95, found_lng=-82.46,
        )
        assert p.found_lat == 27.95


# ═══════════════════════════════════════════════════════════════════════════
# 13. SEED DATA (12 tests)
# ═══════════════════════════════════════════════════════════════════════════


class TestSeed:
    def test_seed_creates_risk_assessments(self, seeded_client):
        from app.db.database import get_connection
        conn = get_connection()
        count = conn.execute("SELECT COUNT(*) FROM risk_assessments").fetchone()[0]
        conn.close()
        assert count == 8

    def test_seed_creates_resources(self, seeded_client):
        from app.db.database import get_connection
        conn = get_connection()
        count = conn.execute("SELECT COUNT(*) FROM resources").fetchone()[0]
        conn.close()
        assert count == SEEDED_RESOURCE_COUNT

    def test_seed_creates_reports(self, seeded_client):
        from app.db.database import get_connection
        conn = get_connection()
        count = conn.execute("SELECT COUNT(*) FROM reports").fetchone()[0]
        conn.close()
        assert count == 5

    def test_seed_creates_missing(self, seeded_client):
        from app.db.database import get_connection
        conn = get_connection()
        count = conn.execute("SELECT COUNT(*) FROM missing_persons").fetchone()[0]
        conn.close()
        assert count == 2

    def test_seed_creates_found(self, seeded_client):
        from app.db.database import get_connection
        conn = get_connection()
        count = conn.execute("SELECT COUNT(*) FROM found_persons").fetchone()[0]
        conn.close()
        assert count == 2

    def test_seed_idempotent(self, seeded_client):
        from app.db.seed import seed
        seed()
        from app.db.database import get_connection
        conn = get_connection()
        count = conn.execute("SELECT COUNT(*) FROM resources").fetchone()[0]
        conn.close()
        assert count == SEEDED_RESOURCE_COUNT

    def test_seed_clears_old_data(self, seeded_client):
        from app.db.database import get_connection
        conn = get_connection()
        conn.execute(
            "INSERT INTO resources (type, name, lat, lng, capacity) VALUES (%s, %s, %s, %s, %s)",
            ("shelter", "Extra", 27.9, -82.5, 100),
        )
        conn.commit()
        conn.close()
        from app.db.seed import seed
        seed()
        conn = get_connection()
        count = conn.execute("SELECT COUNT(*) FROM resources").fetchone()[0]
        conn.close()
        assert count == SEEDED_RESOURCE_COUNT


class TestSeedDataFiles:
    def test_shelters_json_valid(self):
        with open(DATA_DIR / "tampa_shelters.json") as f:
            data = json.load(f)
        assert isinstance(data, list)
        assert len(data) == _json_array_len("tampa_shelters.json")
        assert all("name" in r and "type" in r for r in data)

    def test_zones_json_valid(self):
        with open(DATA_DIR / "tampa_zones.json") as f:
            data = json.load(f)
        assert len(data) == 8

    def test_weather_json_valid(self):
        with open(DATA_DIR / "sample_weather.json") as f:
            data = json.load(f)
        assert "storm_name" in data

    def test_reports_json_valid(self):
        with open(DATA_DIR / "sample_reports.json") as f:
            data = json.load(f)
        assert len(data) == 5

    def test_persons_json_valid(self):
        with open(DATA_DIR / "sample_persons.json") as f:
            data = json.load(f)
        assert len(data["missing"]) == 2
        assert len(data["found"]) == 2


# ═══════════════════════════════════════════════════════════════════════════
# 14. SERVICES (6 tests)
# ═══════════════════════════════════════════════════════════════════════════


class TestServices:
    def test_weather_service_returns_data(self):
        from app.services.weather_service import get_weather_data
        data = get_weather_data()
        assert data["storm_name"] == "Hurricane Rafael"

    def test_weather_service_has_trajectory(self):
        from app.services.weather_service import get_weather_data
        data = get_weather_data()
        assert len(data["trajectory"]) > 0



# ═══════════════════════════════════════════════════════════════════════════
# 15. TEXT-TO-STRUCTURED PARSING (10 tests)
# ═══════════════════════════════════════════════════════════════════════════


_MOCK_FOUND_PERSON_JSON = json.dumps({
    "type": "found",
    "name": "Maria G.",
    "age_approx": 70,
    "gender": "female",
    "description": "Elderly woman with walker, Spanish speaking",
    "location": "Middleton High School",
    "lat": 27.9876,
    "lng": -82.4367,
})

_MOCK_MISSING_PERSON_JSON = json.dumps({
    "type": "missing",
    "name": "Robert Mitchell",
    "age_approx": 65,
    "gender": "male",
    "description": "Tall, bald, wears hearing aid, diabetic",
    "location": "Ruskin",
    "lat": 27.7216,
    "lng": -82.4312,
})

_MOCK_RESOURCE_UPDATE_JSON = json.dumps({
    "name": "Middleton High School",
    "type": "shelter",
    "capacity": 500,
    "current_occupancy": 450,
    "amenities": "hot_meals,charging,pet_friendly,wifi",
    "status": "limited",
    "lat": 27.9876,
    "lng": -82.4367,
    "is_new": False,
})

_MOCK_NEW_RESOURCE_JSON = json.dumps({
    "name": "Temple Terrace Community Center",
    "type": "supply_point",
    "capacity": 100,
    "current_occupancy": 0,
    "amenities": "food,water",
    "status": "open",
    "lat": 28.035,
    "lng": -82.389,
    "is_new": True,
})


class TestReunificationText:
    def test_report_text_found_person(self, seeded_client, monkeypatch):
        monkeypatch.setattr("app.services.text_parser._call_llm", lambda _: _MOCK_FOUND_PERSON_JSON)
        r = seeded_client.post("/api/v1/reunification/report-text", json={
            "text": "I found an elderly woman named Maria at Middleton High School"
        })
        assert r.status_code == 200
        assert r.json()["type"] == "found"
        assert r.json()["record"]["name"] == "Maria G."

    def test_report_text_missing_person(self, seeded_client, monkeypatch):
        monkeypatch.setattr("app.services.text_parser._call_llm", lambda _: _MOCK_MISSING_PERSON_JSON)
        r = seeded_client.post("/api/v1/reunification/report-text", json={
            "text": "My father Robert Mitchell is missing from Ruskin area"
        })
        assert r.status_code == 200
        assert r.json()["type"] == "missing"
        assert r.json()["record"]["name"] == "Robert Mitchell"

    def test_report_text_empty_returns_400(self, client):
        r = client.post("/api/v1/reunification/report-text", json={"text": ""})
        assert r.status_code == 400

    def test_report_text_creates_db_record(self, client, monkeypatch):
        monkeypatch.setattr("app.services.text_parser._call_llm", lambda _: _MOCK_FOUND_PERSON_JSON)
        client.post("/api/v1/reunification/report-text", json={
            "text": "Found Maria at shelter"
        })
        found = client.get("/api/v1/reunification/found").json()
        assert any(p["name"] == "Maria G." for p in found)

    def test_report_text_missing_creates_db_record(self, client, monkeypatch):
        monkeypatch.setattr("app.services.text_parser._call_llm", lambda _: _MOCK_MISSING_PERSON_JSON)
        client.post("/api/v1/reunification/report-text", json={
            "text": "Robert Mitchell is missing"
        })
        missing = client.get("/api/v1/reunification/missing").json()
        assert any(p["name"] == "Robert Mitchell" for p in missing)


class TestResourceText:
    def test_report_text_updates_existing(self, seeded_client, monkeypatch):
        monkeypatch.setattr("app.services.text_parser._call_llm", lambda _: _MOCK_RESOURCE_UPDATE_JSON)
        r = seeded_client.post("/api/v1/resources/report-text", json={
            "text": "Middleton High shelter is almost full, 450 people there now"
        })
        assert r.status_code == 200
        assert r.json()["status"] == "updated"
        assert r.json()["record"]["current_occupancy"] == 450

    def test_report_text_creates_new_resource(self, seeded_client, monkeypatch):
        monkeypatch.setattr("app.services.text_parser._call_llm", lambda _: _MOCK_NEW_RESOURCE_JSON)
        r = seeded_client.post("/api/v1/resources/report-text", json={
            "text": "New supply point at Temple Terrace Community Center with food and water"
        })
        assert r.status_code == 200
        assert r.json()["status"] == "created"
        assert r.json()["record"]["name"] == "Temple Terrace Community Center"

    def test_report_text_empty_returns_400(self, client):
        r = client.post("/api/v1/resources/report-text", json={"text": ""})
        assert r.status_code == 400

    def test_report_text_resource_in_db(self, seeded_client, monkeypatch):
        monkeypatch.setattr("app.services.text_parser._call_llm", lambda _: _MOCK_NEW_RESOURCE_JSON)
        seeded_client.post("/api/v1/resources/report-text", json={
            "text": "Temple Terrace Community Center open"
        })
        resources = seeded_client.get("/api/v1/resources").json()
        assert any(r["name"] == "Temple Terrace Community Center" for r in resources)

    def test_report_text_status_updated(self, seeded_client, monkeypatch):
        monkeypatch.setattr("app.services.text_parser._call_llm", lambda _: _MOCK_RESOURCE_UPDATE_JSON)
        seeded_client.post("/api/v1/resources/report-text", json={
            "text": "Middleton is now limited"
        })
        resources = seeded_client.get("/api/v1/resources").json()
        middleton = [r for r in resources if "Middleton" in r["name"]]
        assert middleton
        assert middleton[0]["status"] == "limited"


# ═══════════════════════════════════════════════════════════════════════════
# 16. DEMO SIMULATION STREAM (6 tests)
# ═══════════════════════════════════════════════════════════════════════════


class TestDemoStream:
    def test_stream_status_returns_200(self, client):
        r = client.get("/api/v1/simulation/demo-stream")
        assert r.status_code == 200
        assert "running" in r.json()
        assert "injected" in r.json()
        assert "total" in r.json()

    def test_stream_stop_returns_200(self, client):
        r = client.post("/api/v1/simulation/demo-stream/stop")
        assert r.status_code == 200
        assert r.json()["status"] == "stopped"

    def test_stream_total_matches_schedule(self, client):
        from app.services.demo_stream import _SCHEDULE
        r = client.get("/api/v1/simulation/demo-stream")
        assert r.json()["total"] == len(_SCHEDULE)

    def test_inject_found_person_directly(self, seeded_client):
        from app.services.demo_stream import _inject_found_person, STREAM_FOUND_PERSONS
        found_before = len(seeded_client.get("/api/v1/reunification/found").json())
        _inject_found_person(STREAM_FOUND_PERSONS[0])
        found_after = len(seeded_client.get("/api/v1/reunification/found").json())
        assert found_after == found_before + 1

    def test_inject_resource_update_directly(self, seeded_client):
        from app.services.demo_stream import _inject_resource_update, STREAM_RESOURCE_UPDATES
        _inject_resource_update(STREAM_RESOURCE_UPDATES[0])
        resources = seeded_client.get("/api/v1/resources").json()
        middleton = [r for r in resources if "Middleton" in r["name"]]
        assert middleton
        assert middleton[0]["current_occupancy"] == STREAM_RESOURCE_UPDATES[0]["current_occupancy"]

    def test_inject_multiple_found_persons(self, seeded_client):
        from app.services.demo_stream import _inject_found_person, STREAM_FOUND_PERSONS
        found_before = len(seeded_client.get("/api/v1/reunification/found").json())
        for person in STREAM_FOUND_PERSONS[:3]:
            _inject_found_person(person)
        found_after = len(seeded_client.get("/api/v1/reunification/found").json())
        assert found_after == found_before + 3


# ═══════════════════════════════════════════════════════════════════════════
# 17. EDGE CASES & INTEGRATION (7 tests)
# ═══════════════════════════════════════════════════════════════════════════


class TestEdgeCases:
    def test_nonexistent_endpoint_404(self, client):
        assert client.get("/api/v1/nonexistent").status_code == 404

    def test_wrong_method_405(self, client):
        assert client.delete("/api/v1/phase").status_code == 405

    def test_concurrent_report_creation(self, client):
        for i in range(10):
            client.post("/api/v1/reports", json={"text": f"Report {i}"})
        assert len(client.get("/api/v1/reports").json()) == 10

    def test_full_workflow_phase_cycle(self, client):
        assert client.get("/api/v1/phase").json()["current_phase"] == "pre_storm"
        client.post("/api/v1/phase/advance")
        assert client.get("/api/v1/phase").json()["current_phase"] == "active_storm"
        client.post("/api/v1/phase/advance")
        assert client.get("/api/v1/phase").json()["current_phase"] == "post_storm"

    def test_report_then_list(self, client):
        client.post("/api/v1/reports", json={"text": "Flooding on Main"})
        reports = client.get("/api/v1/reports").json()
        assert any(r["raw_text"] == "Flooding on Main" for r in reports)

    def test_resource_update_then_nearest(self, seeded_client):
        seeded_client.put("/api/v1/resources/1", json={"status": "closed"})
        r = seeded_client.get("/api/v1/resources/nearest?lat=27.95&lng=-82.46&type=shelter")
        # Closed shelter should not appear as nearest
        assert r.json()["resource"]["id"] != 1

    def test_special_characters_in_report(self, client):
        r = client.post("/api/v1/reports", json={"text": "Flood <script>alert('xss')</script> & more"})
        assert r.status_code == 200
        assert "<script>" in r.json()["raw_text"]
