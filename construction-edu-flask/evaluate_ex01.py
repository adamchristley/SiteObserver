"""Replay the privately held EX-01 research dialogue evaluation CSV.

This intentionally does not import or distribute the ground-truth workbook.
Use a private CSV exported from its EX-01 Test Cases sheet. The output contains
metrics and ID-level predictions, not source dialogues or secrets.
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import re
import time
from pathlib import Path

from crs.osha_documents import ingest, search, sources
from crs.workbench import Workbench
from crs_engine import CRSEngine

REQUIRED = ("Turn ID", "Dialogue Name", "User Input", "OSHA Citations", "Expected Status")
CITE = re.compile(r"1926\.(?:650|651|652)")

def run_cases(rows, wb):
    dialogues = {}
    results = []
    for row in rows:
        turn_id = row["Turn ID"]
        dialogue = row["Dialogue Name"]
        question = row["User Input"]
        record = {"turn_id": turn_id, "dialogue": dialogue,
                  "expected_status": row["Expected Status"],
                  "expected_sections": sorted(set(CITE.findall(row["OSHA Citations"])))}
        started = time.monotonic()
        try:
            if dialogue not in dialogues:
                view = wb.create(question)
                dialogues[dialogue] = {"sid": view["scenario_id"], "branch":"base"}
            else:
                current = dialogues[dialogue]
                if re.search(r"\bhypothetical\b|\bwhat if\b", question, re.I) and current["branch"] == "base":
                    name = "ex01_hypothetical"
                    view = wb.branch(current["sid"], name)
                    current["branch"] = name
                existing = wb.view(current["sid"], current["branch"])
                view = wb.revise(current["sid"], question, existing["version"], current["branch"])
            retrieval = search(wb.engine, question, 12)
            matches = retrieval.get("matches", [])
            predicted = sorted(set(x["section_id"] for x in matches))
            expected = set(record["expected_sections"])
            record.update({
                "success": True,
                "version": view["version"],
                "branch": view["branch"],
                "document_index_ready": retrieval["ready"],
                "retrieved_sections": predicted,
                "section_recall": (len(expected & set(predicted)) / len(expected)) if expected else None,
                "rule_decision_ids": [d["decision_id"] for d in view["rule_decisions"]],
                "candidate_decision_ids": [d["decision_id"] for d in view["candidate_decisions"]],
                "reassessed_candidates": view.get("reassessed_candidates", []),
                "changed_keys": view.get("changed_keys", []),
            })
        except Exception as exc:
            # Surface failures honestly; do not impute benchmark scores.
            record.update({"success": False, "error": type(exc).__name__ + ": " + str(exc)})
        record["elapsed_seconds"] = round(time.monotonic() - started, 4)
        results.append(record)
    success = [r for r in results if r["success"]]
    measurable = [r["section_recall"] for r in success if r.get("section_recall") is not None]
    return {
        "summary": {
            "turns": len(results), "successful_turns": len(success),
            "failed_turns": len(results)-len(success),
            "mean_section_recall_at_12": (sum(measurable) / len(measurable)) if measurable else None,
            "mean_elapsed_seconds": sum(r["elapsed_seconds"] for r in results)/max(len(results),1),
            "warning": "Section-recall is a retrieval proxy, not legal accuracy or human-reviewed decision correctness."
        },
        "turns": results,
    }

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--csv", required=True, help="Private CSV exported from EX-01 test cases")
    parser.add_argument("--db", required=True, help="New disposable research SQLite file")
    parser.add_argument("--output", required=True, help="Local JSON report output")
    parser.add_argument("--ingest", action="store_true",
                        help="Download official OSHA source pages into the local DB first")
    parser.add_argument("--allow-llm", action="store_true",
                        help="Use configured LLM and incur its API costs, if applicable")
    args = parser.parse_args()
    if not args.allow_llm:
        for name in ("CRS_LLM_API_KEY","CRS_LLM_BASE_URL","CRS_LLM_MODEL","CRS_EMBEDDING_MODEL"):
            os.environ.pop(name, None)
    os.environ.pop("CRS_DATABASE_URL", None)
    path = Path(args.db).resolve()
    if path.exists():
        parser.error("Use a new SQLite file for each reproducible run")
    wb = Workbench(CRSEngine(path))
    if args.ingest:
        print("Downloading official OSHA sections and appendices; source fingerprints will be recorded.")
        ingest(wb.engine)
    if not sources(wb.engine):
        parser.error("No official OSHA text indexed; pass --ingest")
    with open(args.csv, newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        if any(key not in (reader.fieldnames or []) for key in REQUIRED):
            parser.error("CSV must contain the original EX-01 column headers")
        result = run_cases(reader, wb)
    with open(args.output, "w", encoding="utf-8") as handle:
        json.dump(result, handle, indent=2)
    print(json.dumps(result["summary"], indent=2))

if __name__ == "__main__":
    main()
