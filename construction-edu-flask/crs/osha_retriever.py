"""Offline, source-linked OSHA retrieval for the CRS-RAG research prototype.

The catalog is a checked-in snapshot of selected OSHA provisions, NOT a live
OSHA API and NOT an exhaustive or continuously updated regulatory database.
It records a catalog fingerprint per entry so later edits can be detected.
"""
from __future__ import annotations

import hashlib
import json
import re
from functools import lru_cache
from pathlib import Path

CATALOG_PATH = Path(__file__).with_name("osha_excavation.json")
_TOKEN = re.compile(r"[a-z0-9]+", re.I)


def _fingerprint(entry):
    """Hash our local research summary, not the authoritative OSHA page."""
    fields = (entry["id"], entry["source_url"], entry["summary"])
    raw = json.dumps(fields, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


@lru_cache(maxsize=1)
def _catalog():
    with CATALOG_PATH.open(encoding="utf-8") as stream:
        catalog = json.load(stream)
    ids = set()
    for item in catalog["regulations"]:
        if item["id"] in ids or not item["source_url"].startswith("https://www.osha.gov/"):
            raise ValueError("Invalid catalog: duplicated citation or non-OSHA URL")
        ids.add(item["id"])
    return catalog


def get_regulation(citation):
    """Return the specific research snapshot used by one evaluated decision."""
    catalog = _catalog()
    for item in catalog["regulations"]:
        if item["id"] == citation:
            return {
                "id": item["id"],
                "title": item["title"],
                "summary": item["summary"],
                "source_url": item["source_url"],
                "catalog_version": catalog["catalog_id"],
                "catalog_checked_on": catalog["reviewed_on"],
                "catalog_content_sha256": _fingerprint(item),
                "assessment_supported": bool(item.get("decision_id")),
                "assessment_decision_id": item.get("decision_id"),
                "source_is_live": False,
            }
    return None


def _term_match(term, tokens, query):
    terms = _TOKEN.findall(term.lower())
    if not terms:
        return False
    if len(terms) == 1:
        return terms[0] in tokens
    return re.search(r"\b" + r"\s+".join(map(re.escape, terms)) + r"\b", query) is not None


def retrieve_osha(query="", conditions=None, limit=12):
    """Rank selected official OSHA citations against words and known CRS fields.

    A match indicates *potential relevance*, not applicability or compliance.
    Unrepresented hazards (water, utilities, toxic air) are retrieved by text
    even though the existing assessor cannot evaluate those provisions.
    """
    if not isinstance(query, str) or len(query) > 2000:
        raise ValueError("query must be text of at most 2,000 characters")
    if conditions is None:
        conditions = {}
    if not isinstance(conditions, dict):
        raise ValueError("conditions must be a JSON object")
    if type(limit) is not int or not 1 <= limit <= 20:
        raise ValueError("limit must be an integer from 1 to 20")
    if not query.strip() and not conditions:
        raise ValueError("Provide a query or at least one scenario condition")

    catalog = _catalog()
    lowered = query.lower()
    words = set(_TOKEN.findall(lowered))
    found = []
    for item in catalog["regulations"]:
        hits = [term for term in item["keywords"] if _term_match(term, words, lowered)]
        state_hits = [key for key in item["condition_keys"] if key in conditions
                      and conditions[key] is not None]
        if not hits and not state_hits:
            continue
        # Matches tied to explicit scenario fields are more informative than
        # incidental text mentions. Multiword keyword matches get a boost.
        score = 3 * len(state_hits) + sum(2 if " " in x else 1 for x in hits)
        found.append({
            **get_regulation(item["id"]),
            "relevance_score": score,
            "matched_terms": hits,
            "matched_conditions": state_hits,
        })
    found.sort(key=lambda x: (-x["relevance_score"], x["id"]))
    return {
        "catalog_version": catalog["catalog_id"],
        "catalog_checked_on": catalog["reviewed_on"],
        "source": catalog["source_authority"],
        "scope": catalog["description"],
        "total_catalog_entries": len(catalog["regulations"]),
        "results": found[:limit],
        "total_matches": len(found),
        "warning": (
            "Retrieved citations are potential matches, not legal applicability "
            "findings. The offline catalog is incomplete and may become outdated. "
            "Re-check current OSHA text and applicable state plans."
        ),
    }


def catalogue_versions():
    """Inspection endpoint for the current checked-in research snapshot."""
    catalog = _catalog()
    return {
        "catalog_version": catalog["catalog_id"],
        "catalog_checked_on": catalog["reviewed_on"],
        "source_is_live": False,
        "total_catalog_entries": len(catalog["regulations"]),
        "citations": [{
            "id": item["id"],
            "catalog_content_sha256": _fingerprint(item),
            "source_url": item["source_url"],
            "assessment_supported": bool(item.get("decision_id")),
        } for item in catalog["regulations"]],
    }
