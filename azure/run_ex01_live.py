#!/usr/bin/env python3
"""Private 15-turn EX-01 live research evaluation against the deployed API.

Reads the adviser-provided XLSX locally. Never uploads the workbook to GitHub.
Writes a JSON report containing metrics and turn IDs, not scenario narratives.
Requires SITEOBSERVER_API_KEY in the environment. Calls are metered when the
running app uses Azure OpenAI. Use only with synthetic research dialogues.
"""
import argparse
import json
import os
import re
import sys
from collections import Counter, defaultdict
from hashlib import sha256
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
from xml.etree import ElementTree as ET
from zipfile import ZipFile


def read_workbook(path):
    ns = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
    with ZipFile(path) as archive:
        shared = []
        if "xl/sharedStrings.xml" in archive.namelist():
            root = ET.fromstring(archive.read("xl/sharedStrings.xml"))
            shared = ["".join(x.text or "" for x in si.iter(ns+"t"))
                      for si in root.findall(ns+"si")]
        sheet = ET.fromstring(archive.read("xl/worksheets/sheet1.xml"))
        rows = []
        for row in sheet.findall(".//"+ns+"sheetData/"+ns+"row"):
            cols = {}
            for cell in row.findall(ns+"c"):
                ref = re.match(r"([A-Z]+)", cell.get("r", ""))
                if not ref:
                    continue
                if cell.get("t") == "inlineStr":
                    value = "".join(t.text or "" for t in cell.iter(ns+"t"))
                else:
                    raw = cell.findtext(ns+"v") or ""
                    value = shared[int(raw)] if cell.get("t") == "s" and raw else raw
                cols[ref.group(1)] = value
            rows.append(cols)
    if not rows or rows[0].get("A") != "Turn ID":
        raise ValueError("Expected the EX-01 ground truth workbook, first worksheet")
    cases = [{"id": row.get("A",""), "dialogue": row.get("B",""),
              "text": row.get("C",""), "expected_citations": row.get("E",""),
              "expected_status": row.get("G","")}
             for row in rows[1:] if row.get("A") and row.get("C")]
    if len(cases) != 15:
        raise ValueError(f"Expected 15 turns but found {len(cases)}")
    return cases


def sections(text):
    return set(re.findall(r"1926\.(?:650|651|652)", str(text)))


def paragraphs(cell):
    """Expand section-relative labels and sibling ranges in an adviser citation cell."""
    section = path = None
    out = set()
    roman = "i ii iii iv v vi vii viii ix x".split()
    for m in re.finditer(r"(1926[.]\d+)|([–—-]?)\s*((?:\([a-z0-9]+\))+)", cell):
        if m[1]:
            section, path = m[1], []
            continue
        if not section:
            continue
        parts = re.findall(r"\(([^)]+)\)", m[3])
        if m[2] and path:
            first, last = path[-1], parts[-1]
            seq = roman if first in roman and last in roman else [str(i) for i in range(1,100)]
            for v in seq[seq.index(first)+1:seq.index(last)+1]:
                out.add(section + "".join(f"({k})" for k in path[:-1]+[v]))
            path = path[:-1]+[last]
        else:
            path = parts
            out.add(section + m[3])
    return out


def run(base, xlsx, key, local_api=None):
    base = (base or "").rstrip("/")
    if not local_api and not base.startswith("https://"):
        raise ValueError("HTTPS endpoint required")
    if not local_api and not key:
        raise ValueError("Set SITEOBSERVER_API_KEY in the local environment")
    cases = read_workbook(xlsx)
    state = defaultdict(lambda: {"sid": None, "version": None, "branch": "base"})
    results = []

    def api(path, data=None, method=None):
        url = base + path
        payload = json.dumps(data).encode() if data is not None else None
        headers = {"Authorization": "Bearer " + key, "Accept": "application/json"}
        if payload is not None:
            headers["Content-Type"] = "application/json"
        request = Request(url, headers=headers, data=payload,
                          method=method or ("POST" if payload is not None else "GET"))
        try:
            with urlopen(request, timeout=90) as response:
                return json.load(response)
        except HTTPError as exc:
            raise RuntimeError(f"HTTP {exc.code} from {path}; see server logs") from None
        except URLError:
            raise RuntimeError(f"Cannot connect to {path}; check Azure service status") from None

    if local_api:
        api = local_api
    availability = api("/api/crs/assistant/status")
    if not local_api and not availability.get("model_configured"):
        raise RuntimeError("Azure model is not configured. Live evaluation aborted.")
    if not availability.get("corpus",{}).get("ready"):
        raise RuntimeError("OSHA corpus is unavailable. Live evaluation aborted.")

    corpus = availability["corpus"]
    if corpus.get("edition") != "2025-07-01" or corpus.get("scope") != "full_part_1926":
        raise RuntimeError("Install the annual 2025 Part 1926 corpus before the evaluation.")
    for case in cases:
        turn_id = case["id"]
        match = re.fullmatch(r"EX-01-([ABC])([0-4])", turn_id)
        if not match:
            raise ValueError(f"Unexpected dialogue identifier {turn_id}")
        group = match.group(1)
        session = state[group]
        row = {"turn_id": turn_id, "dialogue": case["dialogue"],
               "expected_status": case["expected_status"]}
        try:
            if turn_id in ("EX-01-A2", "EX-01-B1", "EX-01-C1") and session["sid"]:
                fork = api("/api/crs/scenarios/" + session["sid"] + "/branches",
                           {"name": "hypothetical", "from_branch": "base"})
                session["branch"] = "hypothetical"
                session["version"] = fork["version"]
            data = {"text": case["text"], "branch": session["branch"]}
            if session["sid"]:
                data["scenario_id"] = session["sid"]
                data["expected_version"] = session["version"]
            response = api("/api/crs/assistant", data)
            if not local_api and response.get("mode") != "azure_openai":
                raise RuntimeError("Live inference unavailable on this turn")
            view = response.get("scenario")
            if view:
                session["sid"] = view["scenario_id"]
                session["version"] = view["version"]
            expected = sections(case["expected_citations"])
            retrieved = set()
            for chunk in response.get("retrieved_osha", response.get("cited_osha", [])):
                retrieved |= sections(chunk.get("citation", chunk.get("id", "")))
            model = sections(" ".join(response.get("model_citations", [])))
            expected_paras = paragraphs(case["expected_citations"])
            supported = {p["citation"] for p in response.get("cited_osha", [])
                         if response.get("citation_attribution") == "rule_supported" and p.get("edition") == "2025-07-01"}
            row.update({
                "expected_paragraphs": sorted(expected_paras), "supported_paragraphs": sorted(supported),
                "missing_paragraphs": sorted(expected_paras - supported),
                "extra_paragraphs": sorted(supported - expected_paras),
                "paragraph_recall": len(supported & expected_paras)/len(expected_paras),
                "paragraph_precision": len(supported & expected_paras)/len(supported) if supported else 0,
                "decision_summary": response.get("decision_summary"), "task_decisions": response.get("task_decisions"),
                "answer": response.get("answer"), "facts": view.get("conditions") if view else {},
                "fact_evidence": response.get("fact_evidence"),
                "changed_conditions": response.get("decision_summary", {}).get("changed_conditions"), "warnings": response.get("warnings"),
                "paragraph_evidence": [{k: p.get(k) for k in ("id","citation","text","edition","sha256")}
                                       for p in response.get("cited_osha", [])],
                "actual_status": response.get("status"),
                        "exact_status_match": response.get("status") == case["expected_status"],
                        "mode": response.get("mode"),
                        "citation_attribution": response.get("citation_attribution"),
                        "expected_sections": sorted(expected),
                        "retrieved_sections": sorted(retrieved),
                        "model_cited_sections": sorted(model),
                        "section_recall": len(expected & retrieved)/len(expected) if expected else None,
                        "model_section_recall": len(expected & model)/len(expected) if expected else None,
                        "conflicts_flagged": bool(response.get("conflicts")),
                        "model_dependencies_proposed": len(response.get("dependency_proposals", [])),
                        "candidate_decisions": len(response.get("candidate_decisions", [])),
                        "reassessed": view.get("reassessed_decisions", []) if view else [],
                        "scenario_version": session["version"]})
        except Exception as exc:
            row["error"] = str(exc)
        results.append(row)
        print(turn_id, "OK" if not row.get("error") else "ERROR",
              row.get("actual_status", row.get("error", "")), flush=True)
    good = [x for x in results if not x.get("error")]
    def average(key):
        values = [x[key] for x in good if x.get(key) is not None]
        return round(sum(values)/len(values), 3) if values else None
    summary = {
        "evaluated_at": datetime.now(timezone.utc).isoformat(),
        "dataset": "EX-01 15-turn excavation dialogue ground truth",
        "model_mode": "local_rule_based" if local_api else "live_azure_openai",
        "turn_modes": dict(Counter(r.get("mode","error") for r in results)),
        "workbook_sha256": sha256(Path(xlsx).read_bytes()).hexdigest(),
        "corpus": {k: corpus.get(k) for k in ("edition","archive_sha256","section_count","appendix_count","chunks")},
        "mean_paragraph_recall": average("paragraph_recall"),
        "mean_paragraph_precision": average("paragraph_precision"),
        "turns": len(results), "successful_turns": len(good),
        "errors": len(results)-len(good),
        "exact_status_match_rate": round(sum(bool(r.get("exact_status_match")) for r in results)/len(results), 3),
        "mean_source_section_recall_at_retrieval": average("section_recall"),
        "mean_model_cited_section_recall": average("model_section_recall"),
        "model_citation_attributions": dict(Counter(x.get("citation_attribution", "unknown")
                                                    for x in good)),
        "status_expected": dict(Counter(x["expected_status"] for x in results)),
        "status_actual": dict(Counter(x.get("actual_status", "ERROR") for x in results)),
        "limitations": [
            "Approved describes the defined research task only.",
            "Paragraph overlap does not establish that a finding applies the requirement correctly.",
            "No expert review of inferred facts, reasoning or decision outcomes is included.",
            "Results on a development dialogue are not independent validation."
        ]
    }
    return {"summary": summary, "cases": results}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("workbook", help="Original EX-01_15_Dialogues_Ground_Truth.xlsx")
    parser.add_argument("--local", action="store_true", help="Exercise the Flask API with isolated SQLite and the deterministic extractor")
    parser.add_argument("--base", help="SiteObserver HTTPS base URL")
    parser.add_argument("--output", default="ex01-live-results.json")
    parser.add_argument("--confirm-model-billing", action="store_true")
    args = parser.parse_args()
    if not args.local and not args.confirm_model_billing:
        parser.error("15 live model requests may incur charges: use --confirm-model-billing")
    if args.local:
        from tempfile import TemporaryDirectory
        from unittest.mock import patch
        sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "construction-edu-flask"))
        from app import app
        with TemporaryDirectory() as tmp, patch.dict(os.environ, {
            "CRS_DATABASE_URL": "", "CRS_REQUIRE_DURABLE_DB": "", "CRS_DB_PATH": tmp+"/eval.sqlite",
            "AZURE_OPENAI_API_KEY": "", "CRS_API_KEY": "local-functional-evaluation"
        }):
            client = app.test_client()
            def local_api(path, data=None):
                response = client.open(path, method="POST" if data is not None else "GET", json=data,
                                       headers={"Authorization": "Bearer local-functional-evaluation"})
                if response.status_code >= 400:
                    raise RuntimeError(str(response.json))
                return response.json
            report = run(None, args.workbook, None, local_api)
    else:
        report = run(args.base, args.workbook, os.environ.get("SITEOBSERVER_API_KEY"))
    output = Path(args.output)
    output.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report["summary"], indent=2))
    print(f"Private evaluation report saved: {output.resolve()}")
    if report["summary"]["errors"]:
        sys.exit(1)
