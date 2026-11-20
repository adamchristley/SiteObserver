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
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
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


def run(base, xlsx, key):
    base = base.rstrip("/")
    if not base.startswith("https://"):
        raise ValueError("HTTPS endpoint required")
    if not key:
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

    availability = api("/api/crs/assistant/status")
    if not availability.get("model_configured"):
        raise RuntimeError("Azure model is not configured. Live evaluation aborted.")
    if not availability.get("corpus",{}).get("ready"):
        raise RuntimeError("OSHA corpus is unavailable. Live evaluation aborted.")

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
            view = response.get("scenario")
            if view:
                session["sid"] = view["scenario_id"]
                session["version"] = view["version"]
            expected = sections(case["expected_citations"])
            retrieved = set()
            for chunk in response.get("retrieved_osha", response.get("cited_osha", [])):
                retrieved |= sections(chunk.get("citation", chunk.get("id", "")))
            model = sections(" ".join(response.get("model_citations", [])))
            row.update({"actual_status": response.get("status"),
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
        "model_mode": "live_azure_openai",
        "turns": len(results), "successful_turns": len(good),
        "errors": len(results)-len(good),
        "exact_status_match_rate": average("exact_status_match"),
        "mean_source_section_recall_at_retrieval": average("section_recall"),
        "mean_model_cited_section_recall": average("model_section_recall"),
        "model_citation_attributions": dict(Counter(x.get("citation_attribution", "unknown")
                                                    for x in good)),
        "status_expected": dict(Counter(x["expected_status"] for x in results)),
        "status_actual": dict(Counter(x.get("actual_status", "ERROR") for x in results)),
        "limitations": [
            "Model-generated approvals are intentionally prohibited by this research service.",
            "Section-level recall does not measure paragraph-level correctness.",
            "No expert review of inferred facts, reasoning or decision outcomes is included.",
            "New scenarios are synthetic and persist in the research database."
        ]
    }
    return {"summary": summary, "cases": results}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("workbook", help="Original EX-01_15_Dialogues_Ground_Truth.xlsx")
    parser.add_argument("--base", required=True, help="SiteObserver HTTPS base URL")
    parser.add_argument("--output", default="ex01-live-results.json")
    parser.add_argument("--confirm-model-billing", action="store_true")
    args = parser.parse_args()
    if not args.confirm_model_billing:
        parser.error("15 live model requests may incur charges: use --confirm-model-billing")
    report = run(args.base, args.workbook, os.environ.get("SITEOBSERVER_API_KEY"))
    output = Path(args.output)
    output.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report["summary"], indent=2))
    print(f"Private evaluation report saved: {output.resolve()}")
    if report["summary"]["errors"]:
        sys.exit(1)
