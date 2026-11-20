"""Regression tests for downloaded OSHA RAG, review-only model edges and web auth."""
import json
from pathlib import Path
import pytest

from crs.document_rag import OSHAIndex, parse_official_html, ingest
from crs.assistant import CRSAssistant
from crs_engine import CRSEngine


def _index(tmp_path):
    docs = [
        {"id": "shield", "citation": "1926.652(a)(1)", "chunk": 0,
         "parent": "1926.652", "source_url": "https://www.osha.gov/laws-regs/regulations/standardnumber/1926/1926.652",
         "text": "Each employee in an excavation shall be protected from cave-ins by an adequate protective system."},
        {"id": "ladder", "citation": "1926.651(c)(2)", "chunk": 0,
         "parent": "1926.651", "source_url": "https://www.osha.gov/laws-regs/regulations/standardnumber/1926/1926.651",
         "text": "A stairway, ladder, ramp or other safe means of egress shall be located in trench excavations four feet deep or more."},
    ]
    file = tmp_path / "osha_corpus.json"
    file.write_text(json.dumps({"source_pages": [{"citation": "1926.652"}, {"citation": "1926.651"}],
                                "retrieved_at": "2026-11-20T00:00:00+00:00",
                                "chunks": docs}), encoding="utf-8")
    return OSHAIndex(file)


def test_official_html_paragraphs_are_split_and_cited():
    html = "<html><main><div class='field--name-body'>" + "".join(
        f"<p>1926.652(a)({i})</p><p>Each excavation paragraph contains important cave-in protection obligations and facts {i}.</p>"
        for i in range(1, 6)) + "</div></main></html>"
    records = parse_official_html(
        html, "1926.652",
        "https://www.osha.gov/laws-regs/regulations/standardnumber/1926/1926.652")
    assert len(records) == 5
    assert records[0]["citation"] == "1926.652(a)(1)"
    assert records[0]["sha256"]
    assert records[0]["source_url"].startswith("https://www.osha.gov/")


def test_official_ingestion_includes_content_hash_and_snapshot(tmp_path, monkeypatch):
    from crs import document_rag
    monkeypatch.setattr(document_rag, "SOURCES", {
        "1926.652": "https://www.osha.gov/laws-regs/regulations/standardnumber/1926/1926.652"})
    html = "<html><main>" + "".join(
        f"<div>1926.652(a)({i})</div><div>Protective systems must cover workers and prevent cave-in exposure at sites {i}.</div>"
        for i in range(1, 6)) + "</main></html>"
    snapshot = ingest(tmp_path / "saved.json", fetch=lambda _: html)
    assert len(snapshot["source_pages"]) == 1
    index = OSHAIndex(tmp_path / "saved.json")
    assert index.status()["ready"] is True
    assert index.search("cave-in protective systems")["chunks"]


def test_retrieval_prefers_matching_egress_text(tmp_path):
    index = _index(tmp_path)
    hits = index.search("ladder egress trench")
    assert hits["mode"] == "osha_source_text"
    assert hits["chunks"][0]["citation"] == "1926.651(c)(2)"


def test_missing_documents_are_explicit(tmp_path):
    index = OSHAIndex(tmp_path / "missing.json")
    assert index.status()["ready"] is False
    result = index.search("trench egress ladder")
    assert result["mode"] == "curated_catalog_only"
    assert not result["chunks"]


def test_proposed_edges_are_persisted_and_flagged_on_revisions(tmp_path):
    index = _index(tmp_path)
    engine = CRSEngine(tmp_path / "test.sqlite3")

    def fake_llm(messages):
        content = json.loads(messages[-1]["content"])
        if "now 4 feet" in content["new_message"]:
            return {
                "conditions": {"depth_ft": 4},
                "conflicts": [], "answer": "Depth changed; reassess protections.",
                "status": "Pending Verification", "citations": ["1926.652(a)(1)"],
                "dependencies": [{"decision_id": "shield_coverage", "condition_key": "depth_ft",
                                  "citation": "1926.652(a)(1)"}],
            }
        return {
            "conditions": {"is_trench": True, "depth_ft": 6, "employees_exposed": True},
            "conflicts": [], "answer": "Protection and inspection need verification.",
            "status": "Insufficient Information", "citations": ["1926.652(a)(1)"],
            "dependencies": [{"decision_id": "shield_coverage", "condition_key": "depth_ft",
                              "citation": "1926.652(a)(1)"}],
        }

    assistant = CRSAssistant(engine, index=index, infer=fake_llm)
    first = assistant.analyze("Workers in a 6-foot trench need cave-in protection.")
    assert first["mode"] == "azure_openai"
    assert first["dependency_proposals"][0]["decision_id"] == "shield_coverage"
    sid = first["scenario"]["scenario_id"]
    assert assistant.graph(sid)["proposed_edges"][0]["review_status"] == "proposed"
    second = assistant.analyze("The trench is now 4 feet deep.", scenario_id=sid, expected_version=1)
    assert second["scenario"]["version"] == 2
    assert second["candidate_decisions_flagged"] == ["shield_coverage"]
    assert len(assistant.history(sid)) == 2
    assert engine.get(sid)["conditions"]["depth_ft"] == 4


def test_bad_model_fields_and_fake_citations_do_not_get_persisted(tmp_path):
    index = _index(tmp_path)
    engine = CRSEngine(tmp_path / "case.sqlite3")

    def malicious_llm(_):
        return {"conditions": {"depth_ft": 6, "confirmed_safe": True},
                "answer": "Approved for work", "status": "Approved",
                "citations": ["1926.999(fake)"],
                "dependencies": [{"decision_id": "fake", "condition_key": "confirmed_safe",
                                  "citation": "1926.999(fake)"}]}

    assistant = CRSAssistant(engine, index=index, infer=malicious_llm)
    response = assistant.analyze("6 foot trench")
    assert response["status"] == "Requires Expert Review"
    assert "confirmed_safe" not in response["scenario"]["conditions"]
    assert not response["citations"]
    assert not response["dependency_proposals"]
    assert any("Rejected" in w for w in response["warnings"])


def test_web_password_uses_cookie_and_csrf_not_browser_api_key(tmp_path, monkeypatch):
    from app import app
    monkeypatch.setenv("CRS_WEB_PASSWORD", "example-test-password")
    monkeypatch.setenv("CRS_DB_PATH", str(tmp_path / "web.sqlite3"))
    monkeypatch.delenv("CRS_DATABASE_URL", raising=False)
    monkeypatch.delenv("CRS_REQUIRE_DURABLE_DB", raising=False)
    monkeypatch.delenv("CRS_API_KEY", raising=False)
    old_secret = app.secret_key
    app.secret_key = "test-flask-signature-key"
    try:
        client = app.test_client()
        assert client.post("/api/crs/web/login", json={"password": "wrong"}).status_code == 403
        login = client.post("/api/crs/web/login", json={"password": "example-test-password"},
                            base_url="https://localhost")
        assert login.status_code == 200
        assert login.json["authenticated"] is True
        csrf = login.json["csrf_token"]
        assert client.get("/api/crs/web/session", base_url="https://localhost").json["authenticated"] is True
        endpoint = "/api/crs/scenarios"
        assert client.post(endpoint, json={"conditions": {"is_trench": True}},
                           base_url="https://localhost").status_code == 403
        got = client.post(endpoint, json={"conditions": {"is_trench": True}},
                          headers={"X-CSRF-Token": csrf}, base_url="https://localhost")
        assert got.status_code == 201
        assert got.json["version"] == 1
    finally:
        app.secret_key = old_secret
