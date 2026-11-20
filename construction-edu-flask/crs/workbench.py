"""Versioned research workbench layered on the existing CRS engine.

Existing deterministic OSHA rules remain authoritative *within their narrow
test scope*. LLM proposals and discovered edges are separate, unapproved
records with exact source-chunk provenance.
"""
from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from uuid import uuid4

from crs.extractor import extract_conditions
from crs.model_gateway import ModelError, configured, extract as model_extract, assess as model_assess
from crs.osha_documents import search as document_search, sources as document_sources
from crs_engine import CRSEngine, CRSInputError, CRSVersionConflict

SCHEMA = """
CREATE TABLE IF NOT EXISTS wb_cases (
 scenario_id TEXT NOT NULL, branch TEXT NOT NULL, version INTEGER NOT NULL,
 extra_json TEXT NOT NULL, created_at TEXT NOT NULL,
 PRIMARY KEY (scenario_id, branch)
);
CREATE TABLE IF NOT EXISTS wb_messages (
 id TEXT PRIMARY KEY, scenario_id TEXT NOT NULL, branch TEXT NOT NULL,
 version INTEGER NOT NULL, text TEXT NOT NULL, extraction_json TEXT NOT NULL,
 created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_wb_messages ON wb_messages(scenario_id, branch, version);
CREATE TABLE IF NOT EXISTS wb_decisions (
 scenario_id TEXT NOT NULL, branch TEXT NOT NULL, decision_id TEXT NOT NULL,
 status TEXT NOT NULL, finding TEXT NOT NULL, citation_ids_json TEXT NOT NULL,
 evaluated_version INTEGER NOT NULL, evaluation_count INTEGER NOT NULL,
 stale INTEGER NOT NULL, updated_at TEXT NOT NULL,
 PRIMARY KEY (scenario_id, branch, decision_id)
);
CREATE TABLE IF NOT EXISTS wb_dependencies (
 scenario_id TEXT NOT NULL, branch TEXT NOT NULL, decision_id TEXT NOT NULL,
 dependency_type TEXT NOT NULL, dependency_key TEXT NOT NULL,
 PRIMARY KEY (scenario_id, branch, decision_id, dependency_type, dependency_key)
);
CREATE INDEX IF NOT EXISTS ix_wb_reverse_dependencies ON wb_dependencies
 (scenario_id, branch, dependency_type, dependency_key);
CREATE TABLE IF NOT EXISTS wb_reviews (
 scenario_id TEXT NOT NULL, branch TEXT NOT NULL, decision_id TEXT NOT NULL,
 review_state TEXT NOT NULL, reviewer_note TEXT NOT NULL,
 reviewed_at TEXT NOT NULL, PRIMARY KEY(scenario_id,branch,decision_id)
);
"""

def stamp():
    return datetime.now(timezone.utc).isoformat()

def jsonvalue(s):
    return json.loads(s)

class Workbench:
    def __init__(self, engine=None):
        self.engine = engine or CRSEngine()
        with self.engine._db() as db:
            db.executescript(SCHEMA)

    def _record(self, sid, branch):
        with self.engine._db() as db:
            row = db.execute("SELECT version,extra_json FROM wb_cases "
                             "WHERE scenario_id=? AND branch=?", (sid, branch)).fetchone()
            if row is None:
                raise CRSInputError("Workbench branch is not initialized")
            return {"version": row["version"], "extra_facts": jsonvalue(row["extra_json"])}

    def list_cases(self):
        with self.engine._db() as db:
            rows = db.execute("SELECT scenario_id, branch, version, created_at FROM wb_cases "
                              "ORDER BY created_at DESC LIMIT 30").fetchall()
            return [dict(r) for r in rows]

    def _proposals(self, sid, branch):
        with self.engine._db() as db:
            rows = db.execute("SELECT * FROM wb_decisions WHERE scenario_id=? AND branch=? "
                              "ORDER BY decision_id", (sid, branch)).fetchall()
            decisions = []
            for row in rows:
                deps = db.execute("SELECT dependency_type, dependency_key FROM wb_dependencies "
                                  "WHERE scenario_id=? AND branch=? AND decision_id=? "
                                  "ORDER BY dependency_type,dependency_key",
                                  (sid, branch, row["decision_id"])).fetchall()
                citations = jsonvalue(row["citation_ids_json"])
                review = db.execute("SELECT review_state,reviewer_note,reviewed_at FROM wb_reviews "
                                    "WHERE scenario_id=? AND branch=? AND decision_id=?",
                                    (sid, branch, row["decision_id"])).fetchone()
                linked = []
                for chunk_id in citations:
                    link = db.execute("SELECT citation,source_url,source_sha256 FROM osha_document_chunks "
                                      "WHERE chunk_id=?", (chunk_id,)).fetchone()
                    if link:
                        linked.append({"chunk_id": chunk_id, "citation": link["citation"],
                                       "source_url": link["source_url"],
                                       "source_sha256": link["source_sha256"]})
                decisions.append({
                    "decision_id": row["decision_id"], "finding": row["finding"],
                    "status": row["status"], "citations": citations, "evidence_links": linked,
                    "review_state": review["review_state"] if review else "pending",
                    "reviewer_note": review["reviewer_note"] if review else "",
                    "depends_on": [d["dependency_key"] for d in deps if d["dependency_type"] == "condition"],
                    "evaluated_version": row["evaluated_version"],
                    "evaluation_count": row["evaluation_count"], "stale": bool(row["stale"]),
                    "source": "llm_candidate", "human_review_required": True})
            return decisions

    def view(self, sid, branch="base"):
        core = self.engine.get(sid, branch)
        wb = self._record(sid, branch)
        with self.engine._db() as db:
            messages = [dict(row) for row in db.execute(
                "SELECT id, version, text, extraction_json, created_at "
                "FROM wb_messages WHERE scenario_id=? AND branch=? ORDER BY version",
                (sid, branch)).fetchall()]
        for item in messages:
            item["extraction"] = jsonvalue(item.pop("extraction_json"))
        return {
            "scenario_id": sid, "branch": branch, "version": wb["version"],
            "core_version": core["version"], "conditions": core["conditions"],
            "extra_facts": wb["extra_facts"], "rule_decisions": core["decisions"],
            "candidate_decisions": self._proposals(sid, branch),
            "messages": messages, "history": self.engine.history(sid, branch),
            "model_configured": configured(), "documents": document_sources(self.engine),
            "warning": "Research prototype only. LLM assessments require expert review; not jobsite clearance."
        }

    def _extract(self, text, conditions=None, extra=None):
        if not isinstance(text, str) or not text.strip() or len(text) > 2000:
            raise CRSInputError("Message must contain 1 to 2,000 characters")
        if configured():
            return model_extract(text, conditions, extra)
        parsed = extract_conditions(text)
        return {"conditions": parsed["conditions"], "extra_facts": {},
                "uncertainties": ["No LLM configured; free-text understanding is limited"]}

    def create(self, text):
        parsed = self._extract(text)
        if not parsed["conditions"]:
            raise CRSInputError("At least one recognized excavation fact is needed to start a case")
        core = self.engine.create(parsed["conditions"])
        sid = core["scenario_id"]
        now = stamp()
        with self.engine._db() as db:
            db.execute("INSERT INTO wb_cases VALUES (?,?,?,?,?)",
                       (sid, "base", 1, json.dumps(parsed["extra_facts"]), now))
        assessment = self._assess(sid, "base", text, core, parsed["extra_facts"], [], None)
        self._store_turn(sid, "base", 1, text, parsed, assessment)
        result = self.view(sid)
        result["reassessed_candidates"] = [p["decision_id"] for p in assessment]
        return result

    def revise(self, sid, text, expected_version, branch="base"):
        if type(expected_version) is not int or expected_version < 1:
            raise CRSInputError("expected_version must be a positive integer")
        if not re.fullmatch(r"[A-Za-z0-9_-]{1,50}", branch):
            raise CRSInputError("Invalid branch name")
        # Explicit hypothetical language must never silently alter actual state.
        if branch == "base" and re.search(r"\b(?:what if|hypothetical|suppose|imagine)\b", text or "", re.I):
            raise CRSInputError("Create and select a hypothetical branch before submitting this turn")
        before = self.view(sid, branch)
        if expected_version != before["version"]:
            raise CRSVersionConflict("Stale workbench version")
        parsed = self._extract(text, before["conditions"], before["extra_facts"])
        patch = parsed["conditions"]
        extra = dict(before["extra_facts"])
        changes = set()
        for key, val in parsed["extra_facts"].items():
            if extra.get(key) != val:
                extra[key] = val
                changes.add(key)
        if patch:
            core = self.engine.revise(sid, patch, branch, before["core_version"])
            changes.update(core.get("changed_conditions", {}).keys())
        else:
            core = self.engine.get(sid, branch)
        new_version = expected_version + 1
        # Do not silently lose a turn without a recognized state change: it may
        # ask a fresh question or request an assessment of previously given facts.
        with self.engine._db() as db:
            db.execute("UPDATE wb_cases SET version=?,extra_json=? "
                       "WHERE scenario_id=? AND branch=? AND version=?",
                       (new_version, json.dumps(extra), sid, branch, expected_version))
            if changes:
                for key in changes:
                    rows = db.execute("SELECT decision_id FROM wb_dependencies "
                                      "WHERE scenario_id=? AND branch=? AND dependency_type='condition' "
                                      "AND dependency_key=?", (sid, branch, key)).fetchall()
                    for row in rows:
                        db.execute("UPDATE wb_decisions SET stale=1 WHERE scenario_id=? AND branch=? "
                                   "AND decision_id=?", (sid, branch, row["decision_id"]))
        old = before["candidate_decisions"]
        affected = sorted({x["decision_id"] for x in old
                           if set(x["depends_on"]) & changes})
        assessment = self._assess(sid, branch, text, core, extra, old, affected)
        self._store_turn(sid, branch, new_version, text, parsed, assessment)
        result = self.view(sid, branch)
        result["changed_keys"] = sorted(changes)
        result["reassessed_candidates"] = [p["decision_id"] for p in assessment]
        return result

    def _assess(self, sid, branch, text, core, extra, old, affected):
        if not configured():
            return []
        query = "OSHA excavation protective systems " + text + " " + " ".join(str(k) + " " + str(v)
                                    for k, v in core["conditions"].items())
        retrieval = document_search(self.engine, query[:4000])
        if not retrieval["ready"]:
            return []
        return model_assess(text, core["conditions"], extra, retrieval, old, affected)

    def _store_turn(self, sid, branch, version, text, parsed, proposals):
        with self.engine._db() as db:
            db.execute("INSERT INTO wb_messages VALUES (?,?,?,?,?,?,?)",
                       (uuid4().hex, sid, branch, version, text,
                        json.dumps(parsed), stamp()))
            for proposal in proposals:
                name = proposal["decision_id"]
                before = db.execute("SELECT evaluation_count FROM wb_decisions "
                                    "WHERE scenario_id=? AND branch=? AND decision_id=?",
                                    (sid, branch, name)).fetchone()
                count = before["evaluation_count"] + 1 if before else 1
                db.execute(
                    "INSERT INTO wb_decisions VALUES (?,?,?,?,?,?,?,?,?,?) "
                    "ON CONFLICT(scenario_id,branch,decision_id) DO UPDATE SET "
                    "status=excluded.status,finding=excluded.finding,"
                    "citation_ids_json=excluded.citation_ids_json,"
                    "evaluated_version=excluded.evaluated_version,"
                    "evaluation_count=excluded.evaluation_count,stale=excluded.stale,"
                    "updated_at=excluded.updated_at",
                    (sid, branch, name, proposal["status"], proposal["finding"],
                     json.dumps(proposal["citations"]), version, count, 0, stamp()))
                db.execute("DELETE FROM wb_reviews WHERE scenario_id=? AND branch=? AND decision_id=?",
                           (sid, branch, name))
                db.execute("DELETE FROM wb_dependencies WHERE scenario_id=? AND branch=? AND decision_id=?",
                           (sid, branch, name))
                for key in proposal["depends_on"]:
                    db.execute("INSERT INTO wb_dependencies VALUES (?,?,?,?,?)",
                               (sid, branch, name, "condition", key))
                for chunk in proposal["citations"]:
                    db.execute("INSERT INTO wb_dependencies VALUES (?,?,?,?,?)",
                               (sid, branch, name, "regulation_chunk", chunk))

    def branch(self, sid, name, from_branch="base"):
        self.engine.branch(sid, name, from_branch)
        before = self._record(sid, from_branch)
        with self.engine._db() as db:
            db.execute("INSERT INTO wb_cases VALUES (?,?,?,?,?)",
                       (sid, name, 1, json.dumps(before["extra_facts"]), stamp()))
            for p in self._proposals(sid, from_branch):
                db.execute("INSERT INTO wb_decisions VALUES (?,?,?,?,?,?,?,?,?,?)",
                           (sid, name, p["decision_id"], p["status"], p["finding"],
                            json.dumps(p["citations"]), 1, 1, int(p["stale"]), stamp()))
                for key in p["depends_on"]:
                    db.execute("INSERT INTO wb_dependencies VALUES (?,?,?,?,?)",
                               (sid, name, p["decision_id"], "condition", key))
                for chunk in p["citations"]:
                    db.execute("INSERT INTO wb_dependencies VALUES (?,?,?,?,?)",
                               (sid, name, p["decision_id"], "regulation_chunk", chunk))
        return self.view(sid, name)

    def review(self, sid, branch, decision_id, action, note=""):
        """Review an LLM-proposed dependency set, never grant worksite approval."""
        self._record(sid, branch)
        if action not in ("accepted", "rejected"):
            raise CRSInputError("Review action must be accepted or rejected")
        if not isinstance(note, str) or len(note) > 500:
            raise CRSInputError("Review note must be 500 characters or less")
        with self.engine._db() as db:
            row = db.execute("SELECT stale FROM wb_decisions WHERE scenario_id=? AND "
                             "branch=? AND decision_id=?", (sid, branch, decision_id)).fetchone()
            if row is None:
                raise CRSInputError("No such model-proposed decision")
            if row["stale"]:
                raise CRSInputError("Stale proposals must be reassessed before review")
            db.execute("INSERT INTO wb_reviews VALUES (?,?,?,?,?,?) "
                       "ON CONFLICT(scenario_id,branch,decision_id) DO UPDATE SET "
                       "review_state=excluded.review_state,reviewer_note=excluded.reviewer_note,"
                       "reviewed_at=excluded.reviewed_at",
                       (sid, branch, decision_id, action, note, stamp()))
        return self.view(sid, branch)
