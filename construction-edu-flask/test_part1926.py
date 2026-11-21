"""Full Part 1926 ingestion, cross-subpart retrieval and generalized research facts."""
from __future__ import annotations

import json
import pytest

from crs.part1926_ingest import parse_part1926, ingest_part1926
from crs.document_rag import OSHAIndex
from crs.assistant import CRSAssistant
from crs_engine import CRSEngine, CRSInputError, validate_changes

NEEDED = {
    "A": ["1926.20", "1926.21"],
    "L": ["1926.451"],
    "M": ["1926.501", "1926.502"],
    "P": ["1926.650", "1926.651", "1926.652"],
    "X": ["1926.1053"],
    "AA": ["1926.1203"],
}


def make_bulk_xml():
    parts = ['<DIV TYPE="PART" N="1910"><HEAD>Part 1910 General Industry</HEAD>'
             '<DIV TYPE="SUBPART" N="Z"><HEAD>Subpart Z</HEAD>'
             '<DIV TYPE="SECTION" N="1910.1200"><P>Irrelevant industry paragraph.</P></DIV>'
             '</DIV></DIV>',
             '<DIV TYPE="PART" N="1926"><HEAD>Part 1926 Construction Safety</HEAD>']
    names = {"L": "Scaffolds", "M": "Fall Protection", "P": "Excavations",
             "X": "Stairways and Ladders", "AA": "Confined Spaces"}
    letters = list("ABCDEFGHIJKLMNOPQRSTUVWX") + ["AA"]
    for idx, code in enumerate(letters):
        parts.append(f'<DIV TYPE="SUBPART" N="{code}"><HEAD>Subpart {code} {names.get(code, "Construction")}</HEAD>')
        for j in range(8):
            num = 1400 + 10 * idx + j
            parts.append(f'<DIV TYPE="SECTION" N="1926.{num}"><HEAD>§ 1926.{num} General work equipment.</HEAD>')
            for k in range(3):
                parts.append(f'<P>({chr(97+k)}) Construction provisions for safe working equipment, '
                             f'workers, tools and inspections in category {code} number {num}.</P>')
            parts.append('</DIV>')
        for section in NEEDED.get(code, []):
            text = ("Guardrail fall arrest safety harness and fall protection equipment" if code == "M"
                    else "Scaffold platform and scaffold guardrails" if code == "L"
                    else "Trench excavation cave-in competent person means of egress" if code == "P"
                    else "Ladder rungs and stairway access" if code == "X"
                    else "Permit required confined space atmospheric hazard" if code == "AA"
                    else "Construction workplace safety rules")
            parts.append(f'<DIV TYPE="SECTION" N="{section}"><HEAD>§ {section} {text}</HEAD>')
            for k in range(3):
                parts.append(f'<P>({chr(97+k)}) {text}; employer duties, training and field verification for workers.</P>')
            parts.append('</DIV>')
        if code == "L":
            parts.append('<DIV TYPE="APPENDIX" N="A"><HEAD>Appendix A to Subpart L of Part 1926</HEAD>'
                         '<P>Scaffold platforms shall be reviewed using official design charts.</P></DIV>')
        parts.append('</DIV>')
    parts.append('</DIV></ROOT>')
    return ('<ROOT>' + ''.join(parts)).replace("<ROOT><ROOT>","<ROOT>").encode()


def test_full_part_not_just_excavations():
    result = parse_part1926(make_bulk_xml())
    assert result["scope"] == "full_part_1926"
    assert result["section_count"] >= 180
    assert len(result["subparts"]) >= 22
    assert result["appendix_count"] >= 1
    assert len(result["chunks"]) >= 500
    sections = {c["section"] for c in result["chunks"] if c["section"]}
    assert {"1926.451", "1926.501", "1926.650", "1926.1053", "1926.1203"} <= sections
    assert "1910.1200" not in sections
    assert any(c["subpart"] == "M" for c in result["chunks"])
    assert any(c["citation"] == "1926 Subpart L App A" for c in result["chunks"])


def test_completeness_gate_rejects_p_only():
    short = b'<ROOT><DIV TYPE="PART" N="1926"><DIV TYPE="SUBPART" N="P"><HEAD>Subpart P Excavations</HEAD><DIV TYPE="SECTION" N="1926.651"><P>Trench digging and inspections.</P></DIV></DIV></DIV></ROOT>'
    with pytest.raises(ValueError, match="Incomplete Part 1926 corpus"):
        parse_part1926(short)


def test_all_part_ingestion_and_subpart_search(tmp_path):
    path = tmp_path / "full.json"
    details = ingest_part1926(path, download=lambda _: make_bulk_xml())
    assert details["scope"] == "full_part_1926"
    assert details["sections"] >= 180
    assert details["chunks"] >= 500
    index = OSHAIndex(path)
    assert index.status()["scope"] == "full_part_1926"
    assert index.status()["section_count"] >= 180
    scaffold = index.search("scaffold platform", subpart="L")
    assert scaffold["chunks"] and all(c["subpart"] == "L" for c in scaffold["chunks"])
    fall = index.search("fall arrest harness", subpart="M")
    assert fall["chunks"] and all(c["subpart"] == "M" for c in fall["chunks"])
    assert any(c["citation"].startswith("1926.501") for c in fall["chunks"])
    assert any(c["citation"].startswith("1926.1053")
               for c in index.search("1926.1053 ladder", subpart="X")["chunks"])
    with pytest.raises(ValueError):
        index.search("scaffold", subpart="M;DROP TABLE")


def test_namespaced_other_construction_facts_are_typed():
    assert validate_changes({"obs_fall_height_ft": 14, "obs_guardrail_present": False}) == {
        "obs_fall_height_ft": 14.0, "obs_guardrail_present": False}
    with pytest.raises(CRSInputError):
        validate_changes({"fall_height_ft": 14})
    with pytest.raises(CRSInputError):
        validate_changes({"obs_guardrail_present": {"untrusted": "nested"}})
    with pytest.raises(CRSInputError):
        validate_changes({"obs_guardrail_present": "x"*1000})


def test_generic_scaffold_observation_dependencies_are_versioned(tmp_path):
    path = tmp_path / "full.json"
    ingest_part1926(path, download=lambda _: make_bulk_xml())
    index = OSHAIndex(path)
    engine = CRSEngine(tmp_path / "full.sqlite3")

    def fake_llm(messages):
        text = json.loads(messages[-1]["content"])["new_message"]
        height = 18 if "18-foot" in text else 12
        return {
            "conditions": {},
            "observations": {"fall_height_ft": height, "guardrail_present": False,
                             "platform_type": "scaffold"},
            "conflicts": [],
            "status": "Pending Verification",
            "answer": "Review fall protection against 1926.501, subject to competent verification.",
            "citations": ["1926.501"],
            "dependencies": [{"decision_id": "fall_protection_review",
                              "condition_key": "fall_height_ft", "citation": "1926.501"}],
            "decisions": [{"decision_id": "fall_protection_review",
                           "status": "requires_review", "rationale": "Unverified guardrails.",
                           "citations": ["1926.501"],
                           "condition_keys": ["fall_height_ft", "guardrail_present"]}],
        }

    assistant = CRSAssistant(engine, index=index, infer=fake_llm)
    first = assistant.analyze("A scaffold platform is 12 feet high without guardrails.")
    assert first["scenario"]["version"] == 1
    assert first["scenario"]["conditions"]["obs_fall_height_ft"] == 12
    assert first["scenario"]["conditions"]["obs_guardrail_present"] is False
    assert first["predefined_rules_scope"] == "excavation_subpart_p_only"
    sid = first["scenario"]["scenario_id"]
    assert assistant.graph(sid)["candidate_decisions"][0]["status"] == "requires_review"
    second = assistant.analyze(
        "Correction: the scaffold platform is 18-foot high.",
        scenario_id=sid, expected_version=1)
    assert second["scenario"]["version"] == 2
    assert second["scenario"]["conditions"]["obs_fall_height_ft"] == 18
    assert "fall_protection_review" in second["candidate_decisions_flagged"]
    assert assistant.graph(sid)["candidate_decisions"][0]["evaluation_count"] == 2
