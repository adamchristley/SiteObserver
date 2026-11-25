"""Index the fixed GovInfo annual part granule, including reserved entries and appendices."""
import argparse
from datetime import datetime, timezone
from hashlib import sha256
import json
from pathlib import Path
import re
from urllib.request import urlopen
import xml.etree.ElementTree as ET

from .document_rag import DEFAULT_PATH, _split

PACKAGE = "CFR-2025-title29-vol8"
URL = f"https://www.govinfo.gov/content/pkg/{PACKAGE}/xml/{PACKAGE}-part1926.xml"
DIGEST = "45e78233491909efdf97293d0be9d7ba548f7a6a7e30a059833418ef3886226d"
EDITION = "2025-07-01"


def plain(node):
    return " ".join("".join(node.itertext()).split())


def paragraph_path(node, context):
    # GPO combines headings and their first child in a single P. Markers in
    # ordinary prose (cross-references) must never become paragraph addresses.
    starts = [node.text or ""] + [e.tail or "" for e in node if e.tag == "E"]
    for start in starts:
        match = re.match(r"^[\s—–-]*((?:\([A-Za-z0-9]+\))+)", start)
        if not match:
            continue
        for label in re.findall(r"\((\w+)\)", match[1]):
            if label.isdigit():
                level = 1
            elif label.isupper():
                level = 3
            elif re.fullmatch(r"[ivx]+", label) and len(context) >= 2 and not (
                    len(label) == 1 and ord(label) == ord(context[0][0]) + 1):
                level = 2
            else:
                level = 0
            context = context[:level] + [label]
    return context


def build(data):
    if sha256(data).hexdigest() != DIGEST:
        raise ValueError("Unexpected annual CFR source digest. Review the edition before reindexing.")
    root = ET.fromstring(data)
    part = root.find("PART")
    if root.findtext("FDSYS/DATE") != EDITION or "PART 1926" not in part.findtext("HD"):
        raise ValueError("Incorrect annual volume or part")
    chunks, sections, appendices, subparts = [], [], [], []
    for sub in part.findall("SUBPART"):
        heading = sub.findtext("HD") or sub.findtext("RESERVED", "")
        code_match = re.match(r"Subpart ([A-Z]+)", heading)
        code = code_match[1] if code_match else None
        if code:
            subparts.append({"code": code, "title": heading})
        for entry in sub.iter():
            if entry.tag not in {"SECTION", "APPENDIX"}:
                continue
            section = None
            if entry.tag == "SECTION":
                section = re.search(r"1926\.[\d.-]+", entry.findtext("SECTNO"))[0]
                title = entry.findtext("SUBJECT") or "Reserved"
                sections.append(section)
                parent = section
            else:
                title = plain(entry.find("HD")) if entry.find("HD") is not None else plain(entry)
                letter = re.search(r"Appendix\s+(\w+)", title, re.I)
                parent = ("1926 Subpart " + code if code else "1926") + " App " + (letter[1] if letter else "reserved")
                appendices.append(parent)
            context = []
            for node in entry:
                if node.tag in {"SECTNO", "PRTPAGE", "EAR"}:
                    continue
                contents = plain(node)
                if not contents and node.tag != "GPH":
                    continue
                citation = parent
                if section and node.tag == "P":
                    context = paragraph_path(node, context)
                    citation += "".join(f"({v})" for v in context)
                graphics = node.tag == "GPH" or node.find(".//GPH") is not None
                for piece in _split(contents or "Consult the graphic in the annual volume."):
                    chunks.append({"id": f"annual-{len(chunks)}", "citation": citation,
                                   "parent": parent, "section": section, "subpart": code,
                                   "subpart_title": heading, "title": title, "text": piece,
                                   "edition": EDITION, "has_graphics": graphics,
                                   "sha256": sha256(piece.encode()).hexdigest(),
                                   "source_url": f"https://www.govinfo.gov/content/pkg/{PACKAGE}/pdf/{PACKAGE}-sec{section.replace('.', '-')}.pdf"
                                   if section else f"https://www.govinfo.gov/content/pkg/{PACKAGE}/pdf/{PACKAGE}-part1926.pdf"})
    # Preserve introductory notes and authorities outside the individual entries.
    for container in [part] + part.findall("SUBPART"):
        title = container.findtext("HD") or container.findtext("RESERVED", "")
        match = re.match(r"Subpart ([A-Z]+)", title)
        for node in container:
            if node.tag not in {"P", "EDNOTE", "AUTH", "SOURCE", "RESERVED"}:
                continue
            for piece in _split(plain(node)):
                chunks.append({"id": f"annual-{len(chunks)}", "citation": title.strip() or "Part 1926",
                               "parent": "Part 1926", "section": None,
                               "subpart": match[1] if match else None, "title": title,
                               "text": piece, "edition": EDITION, "sha256": sha256(piece.encode()).hexdigest(),
                               "source_url": f"https://www.govinfo.gov/content/pkg/{PACKAGE}/pdf/{PACKAGE}-part1926.pdf"})
    if (len(sections), len(appendices), len(subparts)) != (304, 40, 29):
        raise ValueError("Annual structural inventory mismatch")
    return {"scope": "full_part_1926", "edition": EDITION, "archive_sha256": DIGEST,
            "source_archive": URL, "source_pages": sections + appendices,
            "section_count": len(sections), "appendix_count": len(appendices),
            "subparts": subparts, "chunks": chunks,
            "retrieved_at": datetime.now(timezone.utc).isoformat()}


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--xml", type=Path)
    parser.add_argument("--output", type=Path, default=DEFAULT_PATH)
    args = parser.parse_args()
    data = args.xml.read_bytes() if args.xml else urlopen(URL, timeout=90).read()
    result = build(data)
    tmp = args.output.with_suffix(".tmp")
    tmp.write_text(json.dumps(result, ensure_ascii=False))
    tmp.replace(args.output)
    print(result["section_count"], result["appendix_count"], len(result["chunks"]))
