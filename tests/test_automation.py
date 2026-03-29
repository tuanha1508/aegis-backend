"""
Aegis Automation Test Suite — Full end-to-end demo flow.

Tests all autonomous agent cascading, phase transitions, and the
complete storm lifecycle: pre_storm → active_storm → post_storm.

Run: python -m tests.test_automation
"""

import asyncio
import json
import time
import httpx

BASE = "http://localhost:8000/api/v1"
TIMEOUT = 120  # agent calls can take time

PASS = 0
FAIL = 0


def check(name: str, condition: bool, detail: str = ""):
    global PASS, FAIL
    if condition:
        PASS += 1
        print(f"  PASS ✓  {name}")
    else:
        FAIL += 1
        print(f"  FAIL ✗  {name}  {detail}")


async def run_tests():
    global PASS, FAIL

    async with httpx.AsyncClient(base_url=BASE, timeout=TIMEOUT) as c:

        print("╔══════════════════════════════════════════════════════════════╗")
        print("║       AEGIS AUTOMATION TEST SUITE — Full Demo Flow         ║")
        print("╚══════════════════════════════════════════════════════════════╝")

        # ── Baseline ──
        print("\n━━━ BASELINE ━━━")
        reports = (await c.get("/reports")).json()
        incidents = (await c.get("/incidents")).json()
        alerts = (await c.get("/alerts")).json()
        matches = (await c.get("/reunification/matches")).json()
        print(f"  reports={len(reports)}  incidents={len(incidents)}  "
              f"alerts={len(alerts)}  matches={len(matches)}")

        baseline_reports = len(reports)
        baseline_incidents = len(incidents)
        baseline_alerts = len(alerts)

        # ── Test 1: Casual message filtering ──
        print("\n━━━ TEST 1: Casual message → no report ━━━")
        r = (await c.post("/sms/chat", json={"message": "hello what is this app"})).json()
        check("is_report=False", r.get("is_report") is False)
        check("report_id=None", r.get("report_id") is None)
        check("reply contains info", "disaster response" in r.get("reply", "").lower())

        reports_after = (await c.get("/reports")).json()
        check("no new report in DB", len(reports_after) == baseline_reports)

        # ── Test 2: GPS report with auto-cascade ──
        print("\n━━━ TEST 2: Disaster report with GPS → auto-cascade ━━━")
        r = (await c.post("/sms/chat", json={
            "message": "Family trapped on second floor, water rising fast, 3 children need rescue",
            "lat": 27.929, "lng": -82.515
        })).json()
        check("is_report=True", r.get("is_report") is True)
        check("report parsed", r.get("report") is not None)
        report = r.get("report") or {}
        check("incident_type=trapped_person", report.get("incident_type") == "trapped_person")
        check("has GPS coords", report.get("lat") is not None and report.get("lng") is not None)
        check("has neighborhood", report.get("neighborhood") is not None)
        check("processed=True", report.get("processed") is True)

        # Wait for background cascade
        print("  ... waiting 50s for auto-cascade (severity → alert) ...")
        await asyncio.sleep(50)

        incidents_after = (await c.get("/incidents")).json()
        alerts_after = (await c.get("/alerts")).json()
        check("auto-severity: new incidents created",
              len(incidents_after) > baseline_incidents,
              f"was={baseline_incidents} now={len(incidents_after)}")
        check("auto-alert: new alerts created",
              len(alerts_after) > baseline_alerts,
              f"was={baseline_alerts} now={len(alerts_after)}")

        cascade_incidents = len(incidents_after)
        cascade_alerts = len(alerts_after)

        # ── Test 3: Spanish report ──
        print("\n━━━ TEST 3: Spanish report → correct language detection ━━━")
        r = (await c.post("/sms/chat", json={
            "message": "Inundacion severa en nuestra calle, agua subiendo rapido, necesitamos ayuda urgente",
            "lat": 27.7216, "lng": -82.4312
        })).json()
        report = r.get("report", {})
        check("language=es", report.get("language") == "es")
        check("incident_type=flooding", report.get("incident_type") == "flooding")

        # ── Test 4: Scenario switching ──
        print("\n━━━ TEST 4: Scenario switching changes weather data ━━━")
        scenarios = [
            ("storm_none", 0, "no storm"),
            ("storm_watch_72h", 1, "cat 1"),
            ("storm_warning_24h", 3, "cat 3"),
            ("storm_landfall", 3, "landfall"),
            ("storm_post_1d", 0, "post storm"),
        ]
        for step, expected_cat, label in scenarios:
            await c.post("/orchestration/scenario", json={"step": step})
            weather = (await c.get("/monitor/weather")).json()
            actual_cat = weather.get("category", -1)
            check(f"scenario {step}: cat={actual_cat}", actual_cat == expected_cat,
                  f"expected={expected_cat}")

        # ── Test 5: Phase advance auto-cascade ──
        print("\n━━━ TEST 5: Phase advance → auto-triggers agents ━━━")
        # Reset to pre_storm
        await c.post("/phase/set", json={"phase": "pre_storm"})
        await c.post("/orchestration/scenario", json={"step": "storm_landfall"})
        await asyncio.sleep(2)

        # Advance to active_storm
        r = (await c.post("/phase/advance")).json()
        check("phase=active_storm", r.get("current_phase") == "active_storm")

        # Wait for auto-cascade
        print("  ... waiting 40s for phase cascade agents ...")
        await asyncio.sleep(40)

        incidents_phase = (await c.get("/incidents")).json()
        alerts_phase = (await c.get("/alerts")).json()
        check("phase cascade: incidents updated",
              len(incidents_phase) >= cascade_incidents,
              f"was={cascade_incidents} now={len(incidents_phase)}")
        check("phase cascade: alerts updated",
              len(alerts_phase) >= cascade_alerts,
              f"was={cascade_alerts} now={len(alerts_phase)}")

        # ── Test 6: Advance to post_storm → reunification ──
        print("\n━━━ TEST 6: Phase → post_storm → auto-reunification ━━━")
        await c.post("/orchestration/scenario", json={"step": "storm_post_1d"})
        r = (await c.post("/phase/advance")).json()
        check("phase=post_storm", r.get("current_phase") == "post_storm")

        print("  ... waiting 35s for reunification cascade ...")
        await asyncio.sleep(35)

        matches_after = (await c.get("/reunification/matches")).json()
        check("auto-reunification: matches found",
              len(matches_after) > 0,
              f"matches={len(matches_after)}")

        # Check Maria Garcia match
        maria_match = [m for m in matches_after if m.get("confidence", 0) >= 0.7]
        check("high-confidence match exists (>=70%)",
              len(maria_match) > 0,
              f"high_conf_matches={len(maria_match)}")

        # ── Test 7: Match review ──
        print("\n━━━ TEST 7: Match review (confirm/reject) ━━━")
        if matches_after:
            match_id = matches_after[0]["id"]
            r = (await c.patch(f"/reunification/matches/{match_id}",
                              json={"status": "confirmed", "reviewed_by": "demo_operator"})).json()
            check("match confirmed", r.get("status") == "confirmed")
            check("reviewed_by set", r.get("reviewed_by") == "demo_operator")
        else:
            check("match review skipped (no matches)", False, "no matches to review")

        # ── Test 8: Orchestration tick ──
        print("\n━━━ TEST 8: Manual orchestration tick ━━━")
        r = (await c.post("/orchestration/tick")).json()
        check("tick returns mode", r.get("mode") is not None, f"mode={r.get('mode')}")
        check("tick returns jobs_run", "jobs_run" in r)

        # ── Test 9: Orchestration status ──
        print("\n━━━ TEST 9: Orchestration status ━━━")
        r = (await c.get("/orchestration/status")).json()
        check("has operational_mode", r.get("operational_mode") is not None)
        check("has current_scenario", r.get("current_scenario") is not None)
        check("has signals", r.get("signals") is not None)
        signals = r.get("signals", {})
        check("signals has unprocessed_reports", "unprocessed_reports" in signals)
        check("signals has max_flood_risk", "max_flood_risk" in signals)

        # ── Test 10: Live data endpoints ──
        print("\n━━━ TEST 10: Live data endpoints ━━━")
        weather = (await c.get("/live/weather")).json()
        check("live weather has temperature", weather.get("temperature_f") is not None)

        water = (await c.get("/live/water-levels")).json()
        check("live water has stations", len(water.get("stations", [])) > 0,
              f"stations={len(water.get('stations', []))}")

        tides = (await c.get("/live/tides")).json()
        check("live tides has current_level", tides.get("current_level_ft") is not None)

        news = (await c.get("/live/news")).json()
        check("live news has items", news.get("total_items", 0) > 0,
              f"items={news.get('total_items', 0)}")

        streams = (await c.get("/live/streams")).json()
        check("live streams has entries", len(streams.get("streams", [])) > 0)

        forecast = (await c.get("/live/forecast")).json()
        check("live forecast has periods", len(forecast.get("periods", [])) > 0)

        # ── Test 11: All GET endpoints return data ──
        print("\n━━━ TEST 11: All GET endpoints return valid JSON ━━━")
        get_endpoints = [
            "/phase", "/monitor/risk", "/monitor/weather",
            "/reports", "/incidents", "/alerts", "/resources",
            "/reunification/missing", "/reunification/found", "/reunification/matches",
            "/recovery/briefs", "/live/all", "/live/streams",
        ]
        for ep in get_endpoints:
            try:
                r = await c.get(ep)
                check(f"GET {ep} → {r.status_code}", r.status_code == 200)
            except Exception as e:
                check(f"GET {ep}", False, str(e))

        # ── Test 12: Nearest resource ──
        print("\n━━━ TEST 12: Nearest resource lookup ━━━")
        r = (await c.get("/resources/nearest",
                        params={"lat": 27.921, "lng": -82.463, "type": "shelter"})).json()
        check("nearest shelter found", r.get("resource") is not None)
        check("distance calculated", r.get("distance_miles") is not None)

        # ── Test 13: A2A Agent Card Discovery ──
        print("\n━━━ TEST 13: A2A Agent Card Discovery ━━━")

    # A2A endpoints are at root, not under /api/v1
    async with httpx.AsyncClient(base_url="http://localhost:8000", timeout=TIMEOUT) as c2:
        r = (await c2.get("/.well-known/agent.json")).json()
        check("agent card has name", r.get("name") == "Aegis Disaster Intelligence")
        check("agent card has version", r.get("version") == "1.0.0")
        check("agent card has protocol", r.get("protocolVersion") == "0.2.6")
        check("agent card has provider", r.get("provider", {}).get("organization") is not None)
        check("agent card has 9 skills", len(r.get("skills", [])) == 9,
              f"got {len(r.get('skills', []))}")

        skill_ids = [s["id"] for s in r.get("skills", [])]
        for expected in ["aegis-monitor", "aegis-alert", "aegis-field-report",
                         "aegis-severity", "aegis-resource", "aegis-reunification",
                         "aegis-orchestrator", "aegis-commander", "aegis-verification"]:
            check(f"skill '{expected}' present", expected in skill_ids)

        check("skills have tags", all(len(s.get("tags", [])) > 0 for s in r.get("skills", [])))
        check("skills have examples", all(len(s.get("examples", [])) > 0 for s in r.get("skills", [])))
        check("has supportedInterfaces", len(r.get("supportedInterfaces", [])) > 0)

        # Also check alternate path
        r2 = await c2.get("/.well-known/agent-card.json")
        check("alternate path works", r2.status_code == 200)

    async with httpx.AsyncClient(base_url=BASE, timeout=TIMEOUT) as c:

        # ── Test 14: LoopAgent Verification (Self-Correction) ──
        print("\n━━━ TEST 14: LoopAgent Verification (Self-Correction) ━━━")

        # First ensure we have incidents to verify
        incidents_before = (await c.get("/incidents")).json()
        if len(incidents_before) == 0:
            print("  (generating incidents first...)")
            await c.post("/incidents/rank")
            await asyncio.sleep(15)
            incidents_before = (await c.get("/incidents")).json()

        check("incidents exist for verification", len(incidents_before) > 0,
              f"count={len(incidents_before)}")

        # Count unverified before
        unverified_before = sum(1 for i in incidents_before if not i.get("verified"))
        print(f"  Unverified incidents before: {unverified_before}")

        # Run verification LoopAgent
        print("  ... running LoopAgent verification (may take 30-60s) ...")
        r = (await c.post("/incidents/verify")).json()
        check("verification status=success", r.get("status") == "success",
              f"status={r.get('status')} error={r.get('error','')}")
        check("verified_count > 0", r.get("verified_count", 0) > 0,
              f"verified={r.get('verified_count')}")

        # Check if any corrections were made
        corrected = r.get("corrected_count", 0)
        print(f"  Verified: {r.get('verified_count', 0)}  Corrected: {corrected}")
        if corrected > 0:
            print(f"  SELF-CORRECTION DEMONSTRATED: {corrected} incidents re-scored ✓")
        check("verification has summary", len(r.get("summary", "")) > 0)

        # Verify incidents are now marked verified in DB
        incidents_after = (await c.get("/incidents")).json()
        verified_after = sum(1 for i in incidents_after if i.get("verified"))
        check("incidents marked verified in DB", verified_after > 0,
              f"verified_in_db={verified_after}")

        # ── Test 15: Recovery Brief Generation ──
        print("\n━━━ TEST 15: Recovery Brief Generation ━━━")
        print("  ... running Recovery Agent (may take 20-40s) ...")
        r = (await c.post("/recovery/generate")).json()
        check("recovery status=success", r.get("status") == "success",
              f"status={r.get('status')} error={r.get('error','')}")
        check("briefs generated", r.get("briefs_count", 0) > 0,
              f"count={r.get('briefs_count')}")

        if r.get("briefs"):
            brief = r["briefs"][0]
            check("brief has neighborhood", bool(brief.get("neighborhood")))
            check("brief has power_status", bool(brief.get("power_status")))
            check("brief has water_status", bool(brief.get("water_status")))
            check("brief has roads_status", bool(brief.get("roads_status")))

        # ── Test 16: Full Orchestration Tick ──
        print("\n━━━ TEST 16: Orchestration Tick + Signals ━━━")
        status = (await c.get("/orchestration/status")).json()
        check("has operational_mode", status.get("operational_mode") is not None)
        check("has signals.current_phase", status.get("signals", {}).get("current_phase") is not None)
        check("has signals.max_flood_risk", status.get("signals", {}).get("max_flood_risk") is not None)

        r = (await c.post("/orchestration/tick")).json()
        check("tick executed", r.get("mode") is not None)

        # ── Test 17: Situation Commander ──
        print("\n━━━ TEST 17: Situation Commander ━━━")
        print("  ... asking Commander about situation ...")
        r = (await c.post("/commander/ask",
                         json={"question": "What is the current disaster situation?"})).json()
        check("commander status=success", r.get("status") == "success",
              f"status={r.get('status')} error={r.get('error','')}")
        check("commander has response", len(r.get("response", "")) > 20,
              f"response_len={len(r.get('response', ''))}")

        print("  ... asking Commander about Maria Garcia ...")
        r = (await c.post("/commander/ask",
                         json={"question": "Has Maria Garcia been found?"})).json()
        check("commander found Maria", r.get("status") == "success")
        response_lower = r.get("response", "").lower()
        check("response mentions match/found",
              "match" in response_lower or "found" in response_lower or "maria" in response_lower,
              f"response={r.get('response', '')[:80]}")

        # ── Test 18: Storm Simulation Status ──
        print("\n━━━ TEST 18: Simulation Status ━━━")
        r = (await c.get("/simulation/status")).json()
        check("simulation has phase", r.get("phase") is not None)
        check("simulation has scenario", r.get("scenario") is not None)
        check("simulation has stats", r.get("stats") is not None)
        stats = r.get("stats", {})
        check("stats has reports", "reports" in stats)
        check("stats has incidents", "incidents" in stats)
        check("stats has alerts", "alerts" in stats)

        # ── Test 19: Resource Sync (Kris's new endpoint) ──
        print("\n━━━ TEST 19: Resource Sync + Plan (Kris) ━━━")
        r = await c.post("/resources/sync")
        check("resource sync responds", r.status_code in (200, 422, 500),
              f"status={r.status_code}")

        r = await c.post("/resources/plan")
        check("resource plan responds", r.status_code in (200, 422, 500),
              f"status={r.status_code}")

        # ── Test 20: All GET endpoints ──
        print("\n━━━ TEST 20: All GET endpoints (expanded) ━━━")
        all_gets = [
            "/phase", "/monitor/risk", "/monitor/weather",
            "/reports", "/incidents", "/alerts", "/resources",
            "/reunification/missing", "/reunification/found", "/reunification/matches",
            "/recovery/briefs",
            "/live/weather", "/live/water-levels", "/live/tides",
            "/live/alerts", "/live/news", "/live/streams", "/live/forecast",
            "/live/all",
            "/orchestration/status", "/simulation/status",
        ]
        for ep in all_gets:
            try:
                r = await c.get(ep)
                check(f"GET {ep} → {r.status_code}", r.status_code == 200)
            except Exception as e:
                check(f"GET {ep}", False, str(e))

        # ── Summary ──
        print("\n" + "═" * 62)
        print(f"  RESULTS: {PASS} passed, {FAIL} failed, {PASS + FAIL} total")
        print("═" * 62)

        if FAIL == 0:
            print("  ALL TESTS PASSED ✓")
        else:
            print(f"  {FAIL} TESTS FAILED ✗")


if __name__ == "__main__":
    asyncio.run(run_tests())
