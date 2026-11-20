"""Offline workbench integration tests. No paid LLM or live OSHA traffic."""
import pytest

from crs.osha_documents import SOURCES, ingest, parse_osha_html, search, sources
from crs.model_gateway import assess, configured
from crs.workbench import Workbench
from crs_engine import CRSEngine, CRSInputError


def html_for(section):
    return ("<html><main><h1>" + section + " - OSHA excavation standards</h1>"
            + "<p>" + section + "(a) Employers shall assess excavation conditions and "
            "provide protections for exposed employees where the standard requires. "
            "These provisions require a competent person and site-specific review.</p>"
            + "<p>" + section + "(b) The excavation construction process includes "
            "protective systems and worker exposure; record conditions before work "
            "starts and document any changed conditions and required inspections.</p>"
            + "<p>" + section + "(c) Worker protection and excavation safeguards "
            "must be evaluated according to the applicable paragraphs and site conditions.</p>"
            + "</main></html>")


@pytest.fixture
def wb(tmp_path, monkeypatch):
    monkeypatch.delenv("CRS_DATABASE_URL", raising=False)
    monkeypatch.delenv("CRS_LLM_API_KEY", raising=False)
    monkeypatch.delenv("CRS_LLM_MODEL", raising=False)
    monkeypatch.delenv("CRS_LLM_BASE_URL", raising=False)
    return Workbench(CRSEngine(tmp_path / "workbench.sqlite3"))


def test_official_html_ingestion_and_ranked_retrieval(wb):
    with pytest.raises(ValueError):
        parse_osha_html(html_for("1926.651"), "1926.651", "https://evil.test/")
    records = ingest(wb.engine, ["1926.651"], lambda url: html_for("1926.651").encode())
    assert len(records) == 1 and records[0]["chunks"] >= 2
    assert len(sources(wb.engine)) == 1
    hits = search(wb.engine, "1926.651 worker protection excavation")
    assert hits["ready"] and hits["matches"]
    for hit in hits["matches"]:
        assert hit["source_url"] == SOURCES["1926.651"]
        assert hit["citation"].startswith("29 CFR 1926.651")
        assert len(hit["source_sha256"]) == 64
    # Re-indexing must not duplicate source entries.
    ingest(wb.engine, ["1926.651"], lambda url: html_for("1926.651").encode())
    assert sources(wb.engine)[0]["chunks"] == records[0]["chunks"]


def test_multi_turn_versions_and_separate_hypothetical_branch(wb):
    first = wb.create("Workers are inside a 6-foot trench without a protective system.")
    sid = first["scenario_id"]
    assert first["version"] == 1 and first["conditions"]["depth_ft"] == 6
    next_ = wb.revise(sid, "Correction: the trench is 4 feet deep.", 1)
    assert next_["version"] == 2
    assert next_["core_version"] == 2
    assert next_["conditions"]["depth_ft"] == 4
    assert len(next_["messages"]) == 2
    with pytest.raises(CRSInputError):
        wb.revise(sid, "What if the trench is 7 feet deep?", 2)
    alt = wb.branch(sid, "alternative")
    assert alt["branch"] == "alternative"
    hypothetical = wb.revise(sid, "What if the trench is 7 feet deep?", 1, "alternative")
    assert hypothetical["conditions"]["depth_ft"] == 7
    assert wb.view(sid)["conditions"]["depth_ft"] == 4


def test_unknown_english_turn_is_persisted_without_invented_fact(wb):
    first = wb.create("Workers are inside a 6-foot trench.")
    sid = first["scenario_id"]
    answer = wb.revise(sid, "Please explain the evidence available.", 1)
    assert answer["version"] == 2
    assert answer["core_version"] == 1
    assert answer["messages"][-1]["text"].startswith("Please")
    assert answer["candidate_decisions"] == []


def test_model_citations_and_dynamic_graph_are_validated(wb, monkeypatch):
    import crs.model_gateway as gateway
    import crs.workbench as service
    monkeypatch.setenv("CRS_LLM_BASE_URL", "https://example.openai.azure.com/openai/v1")
    monkeypatch.setenv("CRS_LLM_API_KEY", "test-only")
    monkeypatch.setenv("CRS_LLM_MODEL", "test-model")
    ingest(wb.engine, ["1926.651"], lambda url: html_for("1926.651").encode())
    citation = search(wb.engine, "worker protection")["matches"][0]["chunk_id"]
    answer = {"decisions": [{
        "id":"shield_coverage","status":"insufficient_information",
        "finding":"The supplied evidence does not establish the reported shield coverage.",
        "depends_on":["shield_count","depth_ft"],"citations":[citation]}]}
    def mock(messages):
        if "extract only explicit" in messages[0]["content"]:
            if "Correction:" in messages[1]["content"]:
                return {"conditions": {}, "extra_facts":{"shield_count":1}}
            return {"conditions":{"is_trench":True,"depth_ft":18},
                    "extra_facts":{"shield_count":2}}
        return answer
    monkeypatch.setattr(gateway, "_call", mock)
    first = wb.create("An 18-foot trench contains two shields.")
    assert first["extra_facts"]["shield_count"] == 2
    proposal = first["candidate_decisions"][0]
    assert proposal["depends_on"] == ["depth_ft", "shield_count"]
    sid = first["scenario_id"]
    result = wb.revise(sid, "Correction: one shield was removed.", 1)
    assert result["extra_facts"]["shield_count"] == 1
    assert result["changed_keys"] == ["shield_count"]
    assert result["reassessed_candidates"] == ["shield_coverage"]
    assert result["candidate_decisions"][0]["evaluation_count"] == 2
    reviewed = wb.review(sid, "base", "shield_coverage", "accepted", "Dependencies inspected")
    assert reviewed["candidate_decisions"][0]["review_state"] == "accepted"
    assert reviewed["candidate_decisions"][0]["evidence_links"][0]["source_url"].startswith("https://www.osha.gov/")
    ingest(wb.engine, ["1926.651"], lambda _: html_for("1926.651").replace("provide protections","provide adequate protections").encode())
    outdated = wb.view(sid)["candidate_decisions"][0]
    assert outdated["source_outdated"] and outdated["stale"]
    with pytest.raises(CRSInputError, match="changed"):
        wb.review(sid, "base", "shield_coverage", "accepted")
    with pytest.raises(CRSInputError):
        wb.review(sid, "base", "shield_coverage", "compliant")
    assert "shield_coverage" in [x["decision_id"] for x in wb.branch(sid,"alt")["candidate_decisions"]]
    # Hallucinated evidence must be rejected, even when the rest is plausible.
    wrong = dict(answer["decisions"][0], citations=["fabricated"])
    monkeypatch.setattr(gateway, "_call", lambda _: {"decisions":[wrong]})
    assert assess("question", {"depth_ft":18}, {"shield_count":2},
                  search(wb.engine, "worker protection")) == []


def test_browser_login_csrf_and_scenario_routes(wb, tmp_path, monkeypatch):
    from app import app
    from crs import osha_documents
    monkeypatch.setenv("CRS_WEB_PASSWORD", "localsecretpassword123")
    monkeypatch.setenv("CRS_WEB_SESSION_SECRET", "a-very-long-signed-session-test-secret-12345")
    monkeypatch.setenv("CRS_DB_PATH", str(tmp_path / "browser.sqlite3"))
    monkeypatch.setattr(osha_documents, "download_section",
                        lambda section, fetch=None: parse_osha_html(html_for(section), section, SOURCES[section]))
    app.secret_key = "a-very-long-signed-session-test-secret-12345"
    app.config["SESSION_COOKIE_SECURE"] = False
    client = app.test_client()
    assert client.get("/research").status_code == 200
    assert client.get("/api/workbench/status").status_code == 401
    assert client.post("/api/workbench/login", json={"password":"bad"}).status_code == 401
    auth = client.post("/api/workbench/login", json={"password":"localsecretpassword123"})
    assert auth.status_code == 200
    assert client.post("/api/workbench/scenarios", json={"text":"A 6-foot trench"}).status_code == 403
    csrf = {"X-CSRF-Token": auth.json["csrf"]}
    created = client.post("/api/workbench/scenarios",
                          json={"text":"A 6-foot trench"}, headers=csrf)
    assert created.status_code == 201
    sid = created.json["scenario_id"]
    resp = client.post("/api/workbench/scenarios/"+sid+"/messages",
                       json={"text":"The trench is now 4 feet deep.","expected_version":1},
                       headers=csrf)
    assert resp.status_code == 200
    assert resp.json["conditions"]["depth_ft"] == 4
    assert client.post("/api/workbench/ingest", json={"sections":["1926.651"]},
                       headers=csrf).status_code == 200
    hits = client.post("/api/workbench/search",
                       json={"query":"excavation worker protection"},headers=csrf)
    assert hits.status_code == 200 and hits.json["matches"]


def test_appendix_source_is_identified():
    html = ("<main><h1>Appendix A to Subpart P - Soil Classification</h1>"
            "<p>Type C soil includes low strength cohesive soils and granular materials "
            "requiring careful competent-person classification and evaluation.</p>"
            "<p>A visual and manual analysis of the ground and excavation conditions "
            "is required before choosing a protective system in relevant situations.</p>"
            "<p>Changes in environmental conditions may require reclassification and "
            "additional verification before site decisions are revised.</p></main>")
    chunks = parse_osha_html(html, "AppA", SOURCES["AppA"])
    assert len(chunks) >= 2
    assert all(x["citation"] == "29 CFR 1926 Subpart P Appendix A" for x in chunks)


def test_private_ex01_replay_reports_without_raw_dialogue(wb):
    from evaluate_ex01 import run_cases
    ingest(wb.engine, ["1926.651"], lambda url: html_for("1926.651").encode())
    test_rows = [
        {"Turn ID":"EX-01-A0","Dialogue Name":"A","User Input":"A 6-foot trench.",
         "OSHA Citations":"29 CFR 1926.651(c)(2)", "Expected Status":"Insufficient Information"},
        {"Turn ID":"EX-01-A1","Dialogue Name":"A","User Input":"The trench is now 4 feet deep.",
         "OSHA Citations":"29 CFR 1926.651(c)(2)", "Expected Status":"Pending Verification"},
        {"Turn ID":"EX-01-B0","Dialogue Name":"B","User Input":"A new 5-foot trench.",
         "OSHA Citations":"29 CFR 1926.651(k)(1)", "Expected Status":"Insufficient Information"},
    ]
    out = run_cases(test_rows, wb)
    assert out["summary"]["turns"] == 3
    assert out["summary"]["successful_turns"] == 3
    assert out["turns"][1]["version"] == 2
    assert out["turns"][2]["version"] == 1
    assert all("User Input" not in str(record) for record in out["turns"])
