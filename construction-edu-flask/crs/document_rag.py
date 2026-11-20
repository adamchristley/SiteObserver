"""Offline OSHA source corpus and citation-aware retrieval.

Run the ingestion command during a controlled build. Runtime searches NEVER
download remote material. The source text is a timestamped research snapshot.
"""
from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone
from hashlib import sha256
from html import unescape
from math import log
from pathlib import Path
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError
from xml.etree import ElementTree as ET
import argparse
import json
import os
import re

BASE = "https://www.osha.gov/laws-regs/regulations/standardnumber/1926/"
SOURCES = {
    "1926.650": BASE + "1926.650",
    "1926.651": BASE + "1926.651",
    "1926.652": BASE + "1926.652",
    **{f"1926 Subpart P App {letter}": BASE + f"1926SubpartPApp{letter}" for letter in "ABCDEF"},
}
DEFAULT_PATH = Path(__file__).with_name("data") / "osha_corpus.json"
REFERENCE_2025_DIR = DEFAULT_PATH.parent / "reference_2025"
CITE_RE = re.compile(r"^(1926\.(?:650|651|652)(?:\([a-z0-9]+\)){1,8})(?:\s+(.+))?$", re.I)
TOKEN = re.compile(r"[a-z0-9]+", re.I)
STOP = set("the a an and or of to is in on as are for by with from that what how when does this those they have was which about need should into within would will at be".split())


def _normal(text):
    return re.sub(r"\s+", " ", unescape(text)).strip()


def _split(text, width=1100):
    """Split long paragraphs without losing the official parent citation."""
    text = _normal(text)
    if len(text) <= width:
        return [text] if text else []
    words = text.split()
    blocks, block = [], []
    for word in words:
        if block and len(" ".join(block)) + len(word) + 1 > width:
            blocks.append(" ".join(block))
            block = block[-20:]
        block.append(word)
    if block:
        blocks.append(" ".join(block))
    return blocks


def parse_official_html(html, citation, url):
    """Extract content from the regulation body, not the navigation menu."""
    from bs4 import BeautifulSoup
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup.select("script, style, nav, header, footer, form, noscript"):
        tag.decompose()
    main = (soup.select_one(".field--name-body") or soup.select_one("article")
            or soup.select_one("main") or soup.body or soup)
    # OSHA renders provision identifiers as their own link/text segments.
    lines = [_normal(x) for x in main.stripped_strings]
    lines = [line for line in lines if line]
    records = []
    if citation.startswith("1926."):
        current, text = None, []
        def flush():
            if current and len(" ".join(text)) >= 20:
                for i, part in enumerate(_split(" ".join(text))):
                    records.append({"citation": current, "chunk": i, "text": part,
                                    "source_url": url, "parent": citation})
        for line in lines:
            match = CITE_RE.match(line)
            if match:
                flush()
                current, text = match.group(1), [match.group(2)] if match.group(2) else []
            elif current:
                if line.upper().startswith(("AUTHORITY:", "SOURCE:")):
                    flush()
                    current, text = None, []
                else:
                    text.append(line)
        flush()
    else:
        raw = " ".join(lines)
        # Appendix pages contain important tables; capture all visible body text.
        marker = re.search(r"Appendix\s+[A-F]\s+to\s+Subpart\s+P", raw, re.I)
        if marker:
            raw = raw[marker.start():]
        for i, part in enumerate(_split(raw, width=1050)):
            records.append({"citation": citation, "chunk": i, "text": part,
                            "source_url": url, "parent": citation})
    # Guard against parsing a CAPTCHA, navigation-only page, or an empty page.
    if (citation.startswith("1926.") and len(records) < 4) or not records:
        raise ValueError(f"No usable OSHA provision text extracted for {citation}")
    for r in records:
        r["id"] = sha256((r["source_url"] + r["citation"] + str(r["chunk"])).encode()).hexdigest()[:20]
        r["sha256"] = sha256(r["text"].encode()).hexdigest()
    return records


def ingest(output=DEFAULT_PATH, fetch=None):
    """Download nine fixed official OSHA pages and write an atomic snapshot."""
    custom_fetch = fetch is not None
    if fetch is None:
        def fetch(url):
            request = Request(url, headers={"User-Agent": "SiteObserver-Research/1.0 (OSHA source archive)",
                                             "Accept": "text/html"})
            with urlopen(request, timeout=30) as response:
                if response.status != 200 or "html" not in response.headers.get("Content-Type", ""):
                    raise ValueError(f"OSHA source did not return HTML: {url}")
                return response.read(3_000_000).decode("utf-8", "replace")
    docs, sources = [], []
    for citation, url in SOURCES.items():
        try:
            html = fetch(url)
        except (HTTPError, URLError):
            if custom_fetch:
                raise
            # GitHub runners may receive 403 from OSHA HTML. GovInfo hosts the
            # same federal regulations in official eCFR bulk XML.
            return ingest_from_govinfo(output)
        chunks = parse_official_html(html, citation, url)
        docs.extend(chunks)
        sources.append({"citation": citation, "url": url,
                        "html_sha256": sha256(html.encode()).hexdigest(),
                        "chunks": len(chunks)})
    snapshot = {"authority": "OSHA 29 CFR 1926 Subpart P",
                "retrieved_at": datetime.now(timezone.utc).isoformat(),
                "source_pages": sources, "chunks": docs, "schema": 1,
                "disclaimer": "Research snapshot, not a current compliance determination."}
    path = Path(output)
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(".tmp")
    temp.write_text(json.dumps(snapshot, ensure_ascii=False, indent=2), encoding="utf-8")
    temp.replace(path)
    return snapshot


def _tokens(text):
    return [t for t in TOKEN.findall(text.lower()) if len(t) > 1 and t not in STOP]


class OSHAIndex:
    def __init__(self, path=None):
        self.path = Path(path or os.getenv("CRS_OSHA_CORPUS_PATH", str(DEFAULT_PATH)))
        self.snapshot = None
        if self.path.is_file():
            self.snapshot = json.loads(self.path.read_text(encoding="utf-8"))
        self.docs = self.snapshot.get("chunks", []) if self.snapshot else []
        self.reference = []
        # The supplied July 2025 CFR is a separate, auditable research baseline.
        # Loading it does not overwrite the newer primary OSHA/eCFR snapshot.
        if path is None and "CRS_OSHA_CORPUS_PATH" not in os.environ:
            for filename in sorted(REFERENCE_2025_DIR.glob("*.json")):
                snapshot = json.loads(filename.read_text(encoding="utf-8"))
                if snapshot.get("edition") != "2025-07-01":
                    raise ValueError(f"Unexpected historical reference edition: {filename}")
                self.reference.extend(snapshot.get("chunks", []))
        self.docs = self.docs + self.reference
        self.tf = [Counter(_tokens(d["citation"] + " " + d["text"])) for d in self.docs]
        self.df = Counter()
        for freq in self.tf:
            self.df.update(freq.keys())
        self.avgdl = sum(map(lambda v: sum(v.values()), self.tf)) / (len(self.tf) or 1)

    def status(self):
        return {"ready": bool(self.docs), "mode": "osha_source_text" if self.docs else "catalog_only",
                "chunks": len(self.docs), "source_pages": len(self.snapshot["source_pages"]) if self.snapshot else 0,
                "reference_2025_chunks": len(self.reference),
                "reference_2025_edition": "2025-07-01" if self.reference else None,
                "retrieved_at": self.snapshot.get("retrieved_at") if self.snapshot else None,
                "historical_reference_only": bool(self.reference) and not bool(self.snapshot)}

    def search(self, query, limit=7):
        if not isinstance(query, str) or not query.strip() or len(query) > 4000:
            raise ValueError("A query of 1 to 4,000 characters is required")
        if type(limit) is not int or not 1 <= limit <= 12:
            raise ValueError("limit must be between 1 and 12")
        if not self.docs:
            # Explicit fallback only. Never describe the old catalog as downloaded OSHA text.
            from .osha_retriever import retrieve_osha
            result = retrieve_osha(query=query[:2000], limit=limit)
            return {"mode": "curated_catalog_only", "chunks": [],
                    "catalog_matches": result["results"],
                    "warning": "Official OSHA pages have not been ingested; document RAG is unavailable."}
        terms = _tokens(query)
        n, average = len(self.docs), max(self.avgdl, 1)
        ranked = []
        for doc, freq in zip(self.docs, self.tf):
            length = max(sum(freq.values()), 1)
            score = 0.0
            for term in set(terms):
                count = freq[term]
                if count:
                    idf = log(1 + (n - self.df[term] + .5) / (self.df[term] + .5))
                    score += idf * (count * 2.5 / (count + 1.5 * (.25 + .75 * length / average)))
            # Citation exact matches are much stronger than generic words.
            for cited in re.findall(r"1926\.(?:650|651|652)(?:\([a-z0-9]+\))*", query, re.I):
                if doc["citation"].startswith(cited):
                    score += 8
            if score > 0:
                ranked.append((score, doc))
        # Prefer the current snapshot on equal lexical relevance. The 2025 PDF
        # remains accessible as versioned evidence, not the default legal authority.
        ranked.sort(key=lambda pair: (-pair[0], bool(pair[1].get("edition"))))
        chunks = [{**doc, "score": round(score, 4)} for score, doc in ranked[:limit]]
        return {"mode": "osha_source_text", "chunks": chunks,
                "retrieved_at": self.snapshot.get("retrieved_at") if self.snapshot else None,
                "warning": "Sources include a current retrieval snapshot and historical 2025 text; check edition and expert applicability."}


def ingest_from_govinfo(output=DEFAULT_PATH, download=None):
    """Fallback to the government-published, full Title 29 eCFR XML archive.

    Only 1926.650 to 1926.652 and Appendix A-F for Subpart P are indexed.
    Each source paragraph carries a section/subparagraph citation where known.
    """
    url = "https://www.govinfo.gov/bulkdata/ECFR/title-29/ECFR-title29.xml"
    if download is None:
        request = Request(url, headers={"User-Agent": "SiteObserver-Research/1.0",
                                        "Accept": "application/xml"})
        with urlopen(request, timeout=90) as response:
            if response.status != 200:
                raise ValueError("GovInfo eCFR source unavailable")
            data = response.read(45_000_001)
            if len(data) > 45_000_000:
                raise ValueError("GovInfo XML exceeds ingestion limit")
    else:
        data = download(url)
    root = ET.fromstring(data)
    chunks, source_pages = [], {}
    wanted = {"1926.650", "1926.651", "1926.652"}

    for node in root.iter():
        kind = node.get("TYPE", "").upper()
        number = node.get("N", "")
        if kind == "SECTION":
            section = re.search(r"1926\.(650|651|652)\b", number)
            if not section:
                continue
            section = section.group(0)
            source_url = SOURCES[section]
            source_pages[section] = source_url
            context = []
            section_paragraphs = list(node.iter("P"))
            # Some eCFR exports use direct text when P is absent.
            if not section_paragraphs:
                section_paragraphs = [node]
            for paragraph in section_paragraphs:
                plain = _normal(" ".join(paragraph.itertext()))
                if len(plain) < 15:
                    continue
                prefix = re.match(r"^((?:\([a-zA-Z0-9]+\))+)", plain)
                if prefix:
                    labels = re.findall(r"\(([a-zA-Z0-9]+)\)", prefix.group(1))
                    for part in labels:
                        level = (0 if len(part) == 1 and part.islower() and not part.isdigit()
                                 else 1 if part.isdigit()
                                 else 2 if re.fullmatch(r"i|ii|iii|iv|v|vi|vii|viii|ix|x", part)
                                 else 3)
                        context = context[:level] + [part]
                citation = section + "".join(f"({x})" for x in context)
                for piece in _split(plain):
                    chunks.append({"citation": citation, "chunk": len(chunks), "text": piece,
                                   "source_url": source_url, "parent": section})
        elif kind == "APPENDIX":
            head = " ".join("".join(tag.itertext()) for tag in node.findall("HEAD"))
            found = re.search(r"Appendix\s+([A-F])\s+to\s+Subpart\s+P", head, re.I)
            if not found or "1926" not in head:
                continue
            key = f"1926 Subpart P App {found.group(1).upper()}"
            source_url = SOURCES[key]
            source_pages[key] = source_url
            text = _normal(" ".join(node.itertext()))
            for piece in _split(text):
                chunks.append({"citation": key, "chunk": len(chunks), "text": piece,
                               "source_url": source_url, "parent": key})

    sections_found = {c["parent"] for c in chunks if c["parent"] in wanted}
    if sections_found != wanted or len(chunks) < 40:
        raise ValueError("Incomplete official GovInfo excavation source; refusing partial corpus")
    for chunk in chunks:
        chunk["id"] = sha256((chunk["citation"] + str(chunk["chunk"]) +
                              chunk["text"]).encode()).hexdigest()[:20]
        chunk["sha256"] = sha256(chunk["text"].encode()).hexdigest()
    snapshot = {"authority": "29 CFR 1926 Subpart P (GovInfo eCFR bulk XML)",
                "retrieved_at": datetime.now(timezone.utc).isoformat(),
                "source_pages": [{"citation": k, "url": v} for k, v in source_pages.items()],
                "source_archive": url, "archive_sha256": sha256(data).hexdigest(),
                "chunks": chunks, "schema": 1,
                "disclaimer": "Official eCFR research snapshot; verify the current regulatory text."}
    path = Path(output)
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(".tmp")
    temp.write_text(json.dumps(snapshot, ensure_ascii=False, indent=2), encoding="utf-8")
    temp.replace(path)
    return snapshot


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Archive official OSHA excavation documents")
    parser.add_argument("--output", default=str(DEFAULT_PATH))
    args = parser.parse_args()
    snapshot = ingest(args.output)
    print(json.dumps({"sources": len(snapshot["source_pages"]), "chunks": len(snapshot["chunks"]),
                      "output": args.output}))
