"""Ingest the ENTIRE 29 CFR Part 1926 from the official GovInfo eCFR bulk XML.

This is build-time ingestion only. All model-facing passages have source and
edition metadata. It is a regulatory text *research index*, not automated
certification of applicability or legal compliance.

Source: https://www.govinfo.gov/bulkdata/ECFR/title-29/ECFR-title29.xml
"""
from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path
from urllib.request import Request, urlopen
from xml.etree import ElementTree as ET
import argparse
import json
import re

from .document_rag import DEFAULT_PATH, _normal, _split

GOVINFO_XML = "https://www.govinfo.gov/bulkdata/ECFR/title-29/ECFR-title29.xml"
OSHA_BASE = "https://www.osha.gov/laws-regs/regulations/standardnumber/1926/"
SECTION = re.compile(r"\b(1926\.\d{1,4}[a-z]?)\b", re.I)
APPENDIX = re.compile(
    r"\bAppendix\s+([A-Z0-9]+)\s+to\s+(?:Subpart\s+([A-Z]{1,2})\s+of\s+)?Part\s+1926\b",
    re.I,
)
SUBPART = re.compile(r"\bSubpart\s+([A-Z]{1,2})\b", re.I)
MIN_SECTIONS = 180
MIN_SUBPARTS = 22
REQUIRED_SECTIONS = {
    "1926.20", "1926.21", "1926.451", "1926.501", "1926.502",
    "1926.650", "1926.651", "1926.652", "1926.1053", "1926.1203",
}
MAX_XML_BYTES = 48_000_000


def _head(node):
    element = next((child for child in node if child.tag.split("}")[-1] == "HEAD"), None)
    return _normal(" ".join(element.itertext())) if element is not None else ""


def _kind(node):
    return node.attrib.get("TYPE", "").upper()


def _part(root):
    matches = []
    for node in root.iter():
        if _kind(node) != "PART":
            continue
        n = node.attrib.get("N", "").strip()
        if n == "1926" or n == "PART 1926" or re.search(r"\bPART\s+1926\b", _head(node), re.I):
            matches.append(node)
    if len(matches) != 1:
        raise ValueError(f"Expected exactly one 29 CFR Part 1926 in official source; found {len(matches)}")
    return matches[0]


def _source_rows(node):
    """Extract paragraphs and table rows, preserving source text and row context."""
    for item in node.iter():
        tag = item.tag.split("}")[-1].upper()
        if tag == "P":
            # Avoid doubling content from a parent paragraph with nested P tags.
            if any(child.tag.split("}")[-1].upper() == "P" for child in item):
                continue
            raw = _normal(" ".join(item.itertext()))
            if raw:
                yield raw
        elif tag == "ROW":
            # Regulatory appendices contain tabular requirements in many rows.
            if any(child.tag.split("}")[-1].upper() == "P" for child in item.iter() if child is not item):
                continue
            cells = [_normal(" ".join(child.itertext())) for child in item
                     if child.tag.split("}")[-1].upper() in {"ENT", "ENTRY", "TD", "TH", "CELL"}]
            cells = [x for x in cells if x]
            if cells:
                yield " | ".join(cells)


def _flatten_chunks(node, *, citation, section, subpart, subpart_title, title, source_url):
    passages = []
    index = 0
    has_graphics = any(tag.tag.split("}")[-1].upper() in {"GPH", "GRAPHIC"} for tag in node.iter())
    for row in _source_rows(node):
        if len(row) < 12:
            continue
        prefix = re.match(r"^\s*((?:\([a-z0-9]+\)){1,5})", row, re.I)
        # Only attach exact paragraph prefixes explicitly present together.
        cite = citation + (prefix.group(1) if prefix and section else "")
        for piece in _split(row, width=1050):
            if len(piece) < 12:
                continue
            passages.append({
                "citation": cite,
                "parent": section or citation,
                "section": section,
                "subpart": subpart,
                "subpart_title": subpart_title,
                "title": title,
                "chunk": index,
                "text": piece,
                "source_url": source_url,
                "source_archive": GOVINFO_XML,
                "edition": None,
                "source_type": "official_ecfr_part1926",
                "has_graphics": has_graphics,
            })
            index += 1
    # A section can contain plain prose without P markup in some exports.
    if not passages:
        content = _normal(" ".join(node.itertext()))
        if len(content) > 45:
            for piece in _split(content, width=1050):
                passages.append({"citation": citation, "parent": section or citation,
                                 "section": section, "subpart": subpart,
                                 "subpart_title": subpart_title, "title": title,
                                 "chunk": index, "text": piece, "source_url": source_url,
                                 "source_archive": GOVINFO_XML, "edition": None,
                                 "source_type": "official_ecfr_part1926",
                                 "has_graphics": False})
                index += 1
    for item in passages:
        item["id"] = sha256(
            (item["citation"] + "|" + item["source_url"] + "|" +
             str(item["chunk"]) + "|" + item["text"]).encode("utf-8")
        ).hexdigest()[:20]
        item["sha256"] = sha256(item["text"].encode("utf-8")).hexdigest()
    return passages


def parse_part1926(xml_data):
    """Return structured, source-verified text from every Part 1926 subpart.

    Prevents incidental 1910, 1928, or unrelated 29 CFR text from leaking into
    the corpus. Fails the build if major construction standards are missing.
    """
    if not isinstance(xml_data, (bytes, str)):
        raise TypeError("xml_data must be XML bytes or text")
    root = ET.fromstring(xml_data)
    part = _part(root)
    chunks, sections, appendices, subparts = [], {}, {}, {}

    def walk(node, subpart=None, subpart_title=""):
        kind = _kind(node)
        if kind == "SUBPART":
            match = SUBPART.search(_head(node))
            code = node.attrib.get("N", "").strip().upper()
            if not re.fullmatch(r"[A-Z]{1,2}", code):
                code = match.group(1).upper() if match else ""
            if code:
                subpart = code
                subpart_title = _head(node)
                subparts[code] = subpart_title
        if kind == "SECTION":
            n = node.attrib.get("N", "")
            match = SECTION.search(n) or SECTION.search(_head(node))
            if match:
                section = match.group(1)
                source_url = OSHA_BASE + section
                passages = _flatten_chunks(
                    node, citation=section, section=section, subpart=subpart,
                    subpart_title=subpart_title, title=_head(node),
                    source_url=source_url)
                if passages:
                    sections[section] = {"citation": section, "subpart": subpart,
                                         "title": _head(node), "url": source_url,
                                         "chunks": len(passages)}
                    chunks.extend(passages)
            return
        if kind == "APPENDIX":
            match = APPENDIX.search(_head(node))
            if match:
                appendix, from_head = match.groups()
                owner = (from_head or subpart or "").upper()
                citation = (f"1926 Subpart {owner} App {appendix.upper()}"
                            if owner else f"1926 App {appendix.upper()}")
                # Use the real, stable Part 1926 official source page rather than
                # manufacturing deep links to appendices that may not exist.
                source_url = OSHA_BASE.rstrip("/")
                passages = _flatten_chunks(
                    node, citation=citation, section=None, subpart=owner or None,
                    subpart_title=subpart_title, title=_head(node),
                    source_url=source_url)
                if passages:
                    appendices[citation] = {
                        "citation": citation, "subpart": owner or None,
                        "title": _head(node), "url": source_url, "chunks": len(passages)}
                    chunks.extend(passages)
            return
        for child in node:
            walk(child, subpart, subpart_title)

    walk(part)
    missing = sorted(REQUIRED_SECTIONS - set(sections))
    if len(sections) < MIN_SECTIONS or len(subparts) < MIN_SUBPARTS or missing:
        raise ValueError(
            f"Incomplete Part 1926 corpus: {len(sections)} sections, "
            f"{len(subparts)} subparts; required sections missing: {missing}. "
            "Refusing to deploy incomplete regulatory coverage."
        )
    if len(chunks) < 500:
        raise ValueError("Part 1926 source text is unexpectedly short")
    return {
        "authority": "29 CFR Part 1926: Safety and Health Regulations for Construction",
        "scope": "full_part_1926",
        "source_archive": GOVINFO_XML,
        "source_type": "official_ecfr_part1926",
        "retrieved_at": datetime.now(timezone.utc).isoformat(),
        "schema": 2,
        "source_pages": list(sections.values()) + list(appendices.values()),
        "section_count": len(sections),
        "appendix_count": len(appendices),
        "subparts": [{"code": c, "title": t}
                     for c, t in sorted(subparts.items())],
        "chunks": chunks,
        "disclaimer": "Text snapshot of Part 1926, not legal advice or field-work clearance. "
                      "Tables and figures need specialist inspection of the official source."
    }


def ingest_part1926(output=DEFAULT_PATH, download=None):
    if download is None:
        request = Request(GOVINFO_XML, headers={
            "User-Agent": "SiteObserver-Research/1.0 (government-source-cache)",
            "Accept": "application/xml, text/xml"})
        with urlopen(request, timeout=100) as response:
            if response.status != 200:
                raise ValueError("Official eCFR XML unavailable")
            xml = response.read(MAX_XML_BYTES + 1)
    else:
        xml = download(GOVINFO_XML)
    if len(xml) > MAX_XML_BYTES:
        raise ValueError("GovInfo XML exceeds the controlled source size limit")
    snapshot = parse_part1926(xml)
    snapshot["archive_sha256"] = sha256(
        xml if isinstance(xml, bytes) else xml.encode("utf-8")
    ).hexdigest()
    path = Path(output)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(snapshot, ensure_ascii=False), encoding="utf-8")
    tmp.replace(path)
    return {
        "output": str(path), "scope": snapshot["scope"],
        "sections": snapshot["section_count"], "subparts": len(snapshot["subparts"]),
        "appendices": snapshot["appendix_count"],
        "chunks": len(snapshot["chunks"]),
        "archive_sha256": snapshot["archive_sha256"],
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Archive all OSHA 29 CFR Part 1926")
    parser.add_argument("--output", default=str(DEFAULT_PATH))
    args = parser.parse_args()
    print(json.dumps(ingest_part1926(args.output), indent=2))
