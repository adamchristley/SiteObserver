"""Fetch official OSHA excavation regulations and retrieve evidence from stored source text.

Only explicitly allowlisted federal OSHA URLs are fetched. Source paragraphs are
stored in the same durable database used by the existing CRS engine. This is a
research index, not a live regulatory determination.
"""
from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone
from hashlib import sha256
from html.parser import HTMLParser
import json
import math
import re
from urllib.request import Request, urlopen

SECTION_BASE = "https://www.osha.gov/laws-regs/regulations/standardnumber/1926/"
SOURCES = {
    "1926.650": SECTION_BASE + "1926.650",
    "1926.651": SECTION_BASE + "1926.651",
    "1926.652": SECTION_BASE + "1926.652",
    **{"App" + letter: SECTION_BASE + "1926SubpartPApp" + letter for letter in "ABCDEF"},
}
TOKEN = re.compile(r"[a-z0-9]+", re.I)
STOP = set("the a an to and in or of for with on from is are was were as by be it that this at not which shall each must into than under who has have its their such other".split())
HEADING = re.compile(r"^(?:1926\.(?:650|651|652)(?:\([a-z0-9iv]+\))*\.?|(?:Appendix [A-F] to Subpart P.*))$", re.I)

SCHEMA = """
CREATE TABLE IF NOT EXISTS osha_document_chunks (
 chunk_id TEXT PRIMARY KEY,
 source_url TEXT NOT NULL,
 section_id TEXT NOT NULL,
 citation TEXT NOT NULL,
 text TEXT NOT NULL,
 source_sha256 TEXT NOT NULL,
 ingested_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_osha_source ON osha_document_chunks(source_url);
CREATE TABLE IF NOT EXISTS osha_vectors (
 chunk_id TEXT PRIMARY KEY, model TEXT NOT NULL, vector_json TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS osha_source_versions (
 source_url TEXT PRIMARY KEY, active_sha256 TEXT NOT NULL, updated_at TEXT NOT NULL
);
"""

class _Text(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.skip = 0
        self.parts = []
        self.tags = []

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style", "nav", "footer", "header"):
            self.skip += 1
        if tag in ("p", "li", "h1", "h2", "h3", "h4", "tr", "div", "br"):
            self.parts.append("\n")

    def handle_endtag(self, tag):
        if tag in ("script", "style", "nav", "footer", "header") and self.skip:
            self.skip -= 1
        if tag in ("p", "li", "h1", "h2", "h3", "h4", "tr", "div"):
            self.parts.append("\n")

    def handle_data(self, data):
        if not self.skip:
            self.parts.append(data)

def _tokens(s):
    return [w for w in TOKEN.findall(s.lower()) if len(w) > 1 and w not in STOP]

def parse_osha_html(html: str, section_id: str, source_url: str, when=None):
    """Extract bounded, citation-tagged text passages from an OSHA HTML page.

    Preservation is intentionally text-first: citations are section identifiers,
    and any apparent subsection reference is retained only when explicitly present.
    """
    if section_id not in SOURCES or source_url != SOURCES[section_id]:
        raise ValueError("Source must be one of the allowlisted official OSHA sections")
    reader = _Text()
    reader.feed(html)
    raw = "\n".join(x.strip() for x in "".join(reader.parts).splitlines() if x.strip())
    # Begin at the first body occurrence of the regulation heading.
    start = (re.search(r"Appendix [A-F] to Subpart P", raw, re.I)
             if section_id.startswith("App") else
             re.search(r"\b" + re.escape(section_id) + r"\s*[-–]\s*", raw))
    if start:
        raw = raw[start.start():]
    if len(raw) < 150:
        raise ValueError("OSHA source text was unexpectedly short")
    if len(raw) > 600_000:
        raise ValueError("OSHA source text exceeded research ingestion limit")
    source_hash = sha256(raw.encode()).hexdigest()
    lines = [s.strip() for s in raw.split("\n") if s.strip()]
    # Capture evidence paragraphs as bounded text windows. Do not make a claim
    # that inferred subparagraph labels are legally authoritative.
    blocks, current = [], []
    for line in lines:
        if len(line) > 4000:
            line = line[:4000]
        if current and (len(" ".join(current)) + len(line) > 1000 or (HEADING.match(line) and len(" ".join(current)) > 90) or (len(line) > 75 and len(" ".join(current)) > 65)):
            blocks.append(" ".join(current))
            current = []
        current.append(line)
    if current:
        blocks.append(" ".join(current))
    output = []
    timestamp = when or datetime.now(timezone.utc).isoformat()
    for i, text in enumerate(blocks):
        if len(text) < 28:
            continue
        # Explicit markers in original text are preferred; fall back to section.
        match = re.search(r"\b" + re.escape(section_id) + r"(?:\([a-z0-9iv]+\))+", text, re.I)
        citation = (("29 CFR " + match.group()) if match else ("29 CFR " + section_id))
        if section_id.startswith("App"):
            citation = "29 CFR 1926 Subpart P Appendix " + section_id[-1]
        chunk_id = sha256((source_url + "|" + str(i) + "|" + text).encode()).hexdigest()[:24]
        output.append({"chunk_id": chunk_id, "source_url": source_url,
                       "section_id": section_id, "citation": citation,
                       "text": text, "source_sha256": source_hash,
                       "ingested_at": timestamp})
    if len(output) < 2:
        raise ValueError("No usable OSHA document paragraphs were parsed")
    return output

def download_section(section_id, fetch=None):
    if section_id not in SOURCES:
        raise ValueError("Unknown OSHA section")
    url = SOURCES[section_id]
    if fetch:
        body = fetch(url)
    else:
        request = Request(url, headers={"User-Agent": "SiteObserver-Research/1.0 (OSHA public-source research)",
                                       "Accept": "text/html"})
        with urlopen(request, timeout=18) as response:
            if response.url != url and not response.url.startswith("https://www.osha.gov/"):
                raise ValueError("Unexpected external redirect")
            body = response.read(1_500_001)
    if len(body) > 1_500_000:
        raise ValueError("OSHA response exceeded size limit")
    return parse_osha_html(body.decode("utf-8", errors="replace"), section_id, url)

def _init(db):
    db.executescript(SCHEMA)

def ingest(engine, sections=None, fetch=None):
    """Update each section atomically after successful extraction. No silent fallback."""
    sections = sections or list(SOURCES)
    if not isinstance(sections, list) or not sections or any(x not in SOURCES for x in sections):
        raise ValueError("Only allowlisted OSHA sections may be ingested")
    completed = []
    for section in sections:
        chunks = download_section(section, fetch)
        with engine._db() as db:
            _init(db)
            # Retain prior snapshots for auditable decision evidence. Only the
            # active source hash participates in current retrieval.
            db.execute("INSERT INTO osha_source_versions VALUES (?,?,?) "
                       "ON CONFLICT(source_url) DO UPDATE SET "
                       "active_sha256=excluded.active_sha256,updated_at=excluded.updated_at",
                       (SOURCES[section], chunks[0]["source_sha256"], chunks[0]["ingested_at"]))
            for item in chunks:
                db.execute(
                    "INSERT INTO osha_document_chunks VALUES (?,?,?,?,?,?,?) "
                    "ON CONFLICT(chunk_id) DO NOTHING",
                    (item["chunk_id"], item["source_url"], item["section_id"],
                     item["citation"], item["text"], item["source_sha256"], item["ingested_at"]))
        completed.append({"section_id": section, "chunks": len(chunks),
                          "source_url": SOURCES[section], "source_sha256": chunks[0]["source_sha256"]})
    return completed

def sources(engine):
    with engine._db() as db:
        _init(db)
        rows = db.execute("SELECT c.section_id, c.source_url, c.source_sha256, c.ingested_at, "
                          "COUNT(*) AS chunks FROM osha_document_chunks c "
                          "JOIN osha_source_versions v ON c.source_url=v.source_url "
                          "AND c.source_sha256=v.active_sha256 "
                          "GROUP BY c.section_id, c.source_url, c.source_sha256, c.ingested_at "
                          "ORDER BY section_id").fetchall()
        return [dict(r) for r in rows]

def search(engine, query, limit=7):
    if not isinstance(query, str) or not query.strip() or len(query) > 4000:
        raise ValueError("Query must be 1 to 4,000 characters")
    if type(limit) is not int or not 1 <= limit <= 15:
        raise ValueError("Limit must be 1 to 15")
    with engine._db() as db:
        _init(db)
        rows = [dict(r) for r in db.execute(
            "SELECT c.chunk_id, c.source_url, c.section_id, c.citation, c.text, c.source_sha256, c.ingested_at "
            "FROM osha_document_chunks c JOIN osha_source_versions v "
            "ON c.source_url=v.source_url AND c.source_sha256=v.active_sha256 "
            "ORDER BY c.chunk_id").fetchall()]
    if not rows:
        return {"ready": False, "matches": [], "indexed_chunks": 0, "warning": "Official OSHA documents must be ingested first"}
    terms = _tokens(query)
    if not terms:
        return {"ready": True, "matches": [], "indexed_chunks": len(rows)}
    docs = [Counter(_tokens(r["text"])) for r in rows]
    df = Counter(t for d in docs for t in d)
    average = sum(sum(d.values()) for d in docs) / len(docs)
    semantic = {}
    retrieval = "BM25 over downloaded OSHA text"
    # Optional dense retrieval, without requiring pgvector or any cloud
    # provisioning. The official source text stays in the existing DB.
    from crs.model_gateway import embeddings_configured, embed_texts, ModelError
    if embeddings_configured():
        with engine._db() as db:
            vector_rows = db.execute(
                "SELECT chunk_id,vector_json FROM osha_vectors WHERE model=?",
                (__import__("os").environ["CRS_EMBEDDING_MODEL"],)).fetchall()
        if vector_rows:
            try:
                query_vector = embed_texts([query[:2000]])[0]
                query_mag = math.sqrt(sum(x*x for x in query_vector))
                for saved in vector_rows:
                    vector = json.loads(saved["vector_json"])
                    if len(vector) == len(query_vector):
                        mag = math.sqrt(sum(x*x for x in vector))
                        if mag and query_mag:
                            semantic[saved["chunk_id"]] = sum(a*b for a,b in zip(query_vector, vector)) / (mag*query_mag)
                retrieval = "Hybrid BM25 + opt-in dense embeddings"
            except (ModelError, ValueError, TypeError):
                retrieval = "BM25 (embedding request failed; semantic ranking unavailable)"
    ranked = []
    for row, freqs in zip(rows, docs):
        length = max(1, sum(freqs.values()))
        score = 0.
        for term in set(terms):
            f = freqs[term]
            if f:
                idf = math.log(1 + (len(docs) - df[term] + .5) / (df[term] + .5))
                score += idf * (f * 2.2) / (f + 1.2 * (0.25 + 0.75 * length / max(1, average)))
        if row["section_id"] in query:
            score += 4
        if row["chunk_id"] in semantic:
            # Use a modest bounded semantic boost; lexical matches remain visible.
            score += 2.5 * max(0.0, semantic[row["chunk_id"]])
        if score > 0:
            ranked.append((score, row))
    ranked.sort(key=lambda pair: (-pair[0], pair[1]["chunk_id"]))
    return {"ready": True, "indexed_chunks": len(rows),
            "retrieval": retrieval,
            "matches": [{**r, "score": round(s, 5)} for s, r in ranked[:limit]],
            "warning": "Research evidence only; confirm legal applicability, currency, and state requirements"}


def build_embeddings(engine, limit=16):
    """Index one limited batch at a time. Requires an approved embeddings service."""
    from crs.model_gateway import embeddings_configured, embed_texts, ModelError
    import os
    if not embeddings_configured():
        raise ModelError("CRS_EMBEDDING_MODEL must be configured on the server")
    if type(limit) is not int or not 1 <= limit <= 16:
        raise ValueError("Embedding batch limit must be 1 to 16")
    model = os.environ["CRS_EMBEDDING_MODEL"]
    with engine._db() as db:
        _init(db)
        rows = [dict(r) for r in db.execute(
            "SELECT c.chunk_id,c.text FROM osha_document_chunks c "
            "JOIN osha_source_versions sv ON c.source_url=sv.source_url "
            "AND c.source_sha256=sv.active_sha256 "
            "LEFT JOIN osha_vectors v ON c.chunk_id=v.chunk_id AND v.model=? "
            "WHERE v.chunk_id IS NULL ORDER BY c.chunk_id LIMIT ?",
            (model,limit)).fetchall()]
    if not rows:
        return {"indexed": 0, "model": model}
    embeddings = embed_texts([r["text"][:2000] for r in rows])
    with engine._db() as db:
        for row, vector in zip(rows, embeddings):
            db.execute("INSERT INTO osha_vectors VALUES (?,?,?) "
                       "ON CONFLICT(chunk_id) DO UPDATE SET "
                       "model=excluded.model,vector_json=excluded.vector_json",
                       (row["chunk_id"], model, json.dumps(vector)))
    return {"indexed": len(rows), "model": model}
