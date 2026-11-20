"""Evaluate CRS-RAG against the 15-turn EX-01 research dialogue workbook.

No test data are uploaded or committed. Default mode is retrieval-only and
makes no model requests. --live explicitly opts in to paid model inference.
"""
from __future__ import annotations

from collections import defaultdict
from pathlib import Path
from tempfile import TemporaryDirectory
from time import perf_counter
from xml.etree import ElementTree as ET
from zipfile import ZipFile
import argparse
import json
import re

from crs.assistant import CRSAssistant, model_available
from crs.document_rag import OSHAIndex
from crs_engine import CRSEngine


def read_workbook(path):
    """Read the first worksheet using the standard XLSX ZIP/XML structure."""
    ns = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
    with ZipFile(path) as archive:
        shared = []
        if "xl/sharedStrings.xml" in archive.namelist():
            root = ET.fromstring(archive.read("xl/sharedStrings.xml"))
            shared = ["".join(t.text or "" for t in si.iter(ns + "t"))
                      for si in root.findall(ns + "si")]
        sheet = ET.fromstring(archive.read("xl/worksheets/sheet1.xml"))
        records = []
        for row in sheet.findall(".//" + ns + "sheetData/" + ns + "row"):
            cols = {}
            for cell in row.findall(ns + "c"):
                name = re.match(r"([A-Z]+)", cell.attrib.get("r", ""))
                if name is None:
                    continue
                kind = cell.attrib.get("t")
                if kind == "inlineStr":
                    value = "".join(t.text or "" for t in cell.iter(ns + "t"))
                else:
                    node = cell.find(ns + "v")
                    raw = node.text if node is not None else ""
                    value = shared[int(raw)] if kind == "s" and raw else raw
                cols[name.group(1)] = value or ""
            records.append(cols)
    if not records or records[0].get("A") != "Turn ID":
        raise ValueError("Expected EX-01 first worksheet with Turn ID header")
    data = [
        {"turn_id": row.get("A", ""), "dialogue": row.get("B", ""),
         "text": row.get("C", ""), "expected_decisions": row.get("D", ""),
         "expected_citations": row.get("E", ""), "expected_updates": row.get("F", ""),
         "expected_status": row.get("G", "")}
        for row in records[1:] if row.get("A") and row.get("C")
    ]
    return data


def citation_sections(text):
    return set(re.findall(r"1926\.(?:650|651|652)", str(text)))


def evaluate(path, live=False):
    cases = read_workbook(path)
    index = OSHAIndex()
    summary = {"case_count": len(cases), "source_status": index.status(),
               "model_available": model_available(), "mode": "live" if live else "retrieval_only",
               "cases": []}
    if live and not model_available():
        raise RuntimeError("Azure model endpoint/deployment/key not configured")
    with TemporaryDirectory(prefix="crs-eval-") as temp:
        assistant = CRSAssistant(CRSEngine(Path(temp) / "research.sqlite3"), index=index) if live else None
        active = defaultdict(lambda: {"sid": None, "branch": "base", "version": None})
        for case in cases:
            start = perf_counter()
            retrieval = index.search(case["text"])
            refs = {x.get("citation", x.get("id")) for x in
                    (retrieval.get("chunks", []) or retrieval.get("catalog_matches", []))}
            expected = citation_sections(case["expected_citations"])
            observed = citation_sections(" ".join(x for x in refs if x))
            record = {
                "turn_id": case["turn_id"], "dialogue": case["dialogue"],
                "expected_status": case["expected_status"],
                "expected_sections": sorted(expected), "retrieved_sections": sorted(observed),
                "section_recall": len(expected & observed) / len(expected) if expected else None,
                "retrieval_mode": retrieval["mode"],
            }
            if live:
                group = case["turn_id"].split("-")[2][0]  # A/B/C
                session = active[group]
                # EX-01 separates the initial factual record from later what-if stages.
                if (case["turn_id"] in {"EX-01-A2", "EX-01-B1", "EX-01-C1"}
                        and session["sid"]):
                    assistant.engine.branch(session["sid"], "hypothetical")
                    session["branch"] = "hypothetical"
                    session["version"] = 1
                response = assistant.analyze(
                    case["text"], scenario_id=session["sid"], branch=session["branch"],
                    expected_version=session["version"])
                scenario = response.get("scenario")
                if scenario:
                    session["sid"], session["version"] = scenario["scenario_id"], scenario["version"]
                record.update({"actual_status": response["status"],
                               "status_matches": response["status"] == case["expected_status"],
                               "version": session["version"],
                               "reassessed": scenario.get("reassessed_decisions", []) if scenario else [],
                               "proposed_dependencies": len(response["dependency_proposals"]),
                               "warnings": response["warnings"]})
            record["latency_ms"] = round((perf_counter() - start) * 1000, 1)
            summary["cases"].append(record)
    rows = summary["cases"]
    recall = [r["section_recall"] for r in rows if r["section_recall"] is not None]
    summary["mean_section_recall"] = round(sum(recall) / len(recall), 3) if recall else None
    summary["mean_latency_ms"] = round(sum(r["latency_ms"] for r in rows) / len(rows), 1) if rows else None
    if live:
        summary["exact_status_match_rate"] = round(
            sum(r.get("status_matches", False) for r in rows) / len(rows), 3) if rows else None
    return summary


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("xlsx", help="Path to the uncommitted EX-01 ground truth workbook")
    parser.add_argument("--output", help="Write a local JSON report")
    parser.add_argument("--live", action="store_true", help="Make real Azure OpenAI model calls")
    parser.add_argument("--confirm-model-billing", action="store_true",
                        help="Explicit acknowledgement of metered model inference")
    args = parser.parse_args()
    if args.live and not args.confirm_model_billing:
        parser.error("--live requires --confirm-model-billing")
    report = evaluate(args.xlsx, live=args.live)
    if args.output:
        Path(args.output).write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps({k: v for k, v in report.items() if k != "cases"}, indent=2))
