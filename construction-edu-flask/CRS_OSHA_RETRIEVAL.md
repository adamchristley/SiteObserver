# CRS-RAG Layer 4: Source-linked OSHA excavation retrieval

The existing natural-language input pipeline, versioned state store, and decision dependency tracker now call an **offline, versioned research catalog** of selected official OSHA excavation provisions. No LLM calls, vector database, or new Azure service is required.

**Scope and safety:** This feature retrieves *potentially relevant citations*, not authoritative determinations of legal applicability, and it does not provide jobsite safety clearance. Catalog entries are short authored summaries of OSHA paragraphs with links to the original source. They are not the official legal text. OSHA regulations can change. Verify current OSHA and applicable state-plan requirements before any real-world use.

## Layer 4 implementation

- `crs/osha_excavation.json`: 12 researched regulatory provisions from 29 CFR 1926 Subpart P; citation IDs, official source URLs, short summaries, keywords, relevant CRS condition keys, and supported-decision IDs.
- `crs/osha_retriever.py`: deterministic ranked retrieval by optional free-text query and/or structured scenario conditions, independent of paid APIs. Returns catalog snapshot identifier, review date, relevant citations, match explanations, and a warning that the offline catalog is incomplete.
- `crs_engine.py`: stores the selected catalog version and SHA-256 of *our local catalog summary* alongside each rule-based decision when evaluated. It does **not** pretend this hash is an OSHA regulatory revision identifier. Existing historical records without this evidence are still readable.
- `app.py`: authenticated retrieval APIs; the existing `CRS_API_KEY` gate applies. Nothing is exposed to unauthenticated browsers.
- `crs/state_resolver.py`: natural-language creation and follow-up replies now include an `osha_retrieval` object, in addition to extracted conditions and structured decisions.

The original four assessments remain rule-based. Other retrieved provisions (such as underground utilities, hazardous atmospheres and water accumulation) are **retrieval-only**, not silently classified as compliant or noncompliant.

## API examples

### Search the curated OSHA catalog

```http
POST /api/crs/osha/search
Authorization: Bearer <your-research-api-key>
Content-Type: application/json

{"query":"Standing water is accumulating near a trench","limit":10}
```

Results include: `id`, `title`, `summary`, `source_url`, `catalog_version`, `catalog_checked_on`, `catalog_content_sha256`, `matched_terms`, `matched_conditions`, `assessment_supported`, and `relevance_score`.

### Search based on a saved scenario

```http
GET /api/crs/scenarios/<scenario_id>/osha
Authorization: Bearer <your-research-api-key>
```

The response contains `retrieval` for the scenario and `assessed_regulations` for the decisions with already-recorded evidence snapshots. An optional `?q=water` or `?branch=what_if` can refine this search.

### Catalog metadata and fingerprints

```http
GET /api/crs/osha/catalog
Authorization: Bearer <your-research-api-key>
```

### Natural-language create and correction

Existing authenticated `POST /api/crs/nl/scenarios` and `POST /api/crs/nl/scenarios/<sid>/messages` now add an `osha_retrieval` object to their responses. Existing `scenario` and `extraction` keys remain unchanged.

## Verification

Install test dependencies and run:

```bash
python -m pip install Flask==3.1.1 pytest
python -m pytest -q construction-edu-flask/test_osha_retrieval.py construction-edu-flask/test_crs.py construction-edu-flask/test_nl_pipeline.py
```

GitHub Actions also runs the PostgreSQL integration test with a local disposable database. None of these CI tests connect to your free Neon production test database.

## Research limitations and next steps

1. **Catalog refresh is manual today.** Version identifiers and content fingerprints support tracking changes between checked-in research snapshots. The system does not automatically fetch new official OSHA text or confirm that the current catalog equals the latest regulation. Add a controlled official-source import and verification process with review logs.
2. **No expanded compliance logic yet.** The 8 additional retrieved provisions are references only. Extend the state schema, formal requirements, and domain expert-reviewed assessment logic before using them for decisions.
3. **Catalog changes require review.** On reading a saved scenario, `catalog_changed_since_evaluation=true` means the local summary changed after the decision was last evaluated. This *flags* potentially stale evidence; it does **not** automatically make the old decision current or trigger recalculation, because such recalculation would need updated rules.
4. **No secure public UI yet.** Keep API keys server-side. Don't put the CRS bearer token in public JS.
5. **No new paid infrastructure.** Keep using Azure Container Apps Consumption + Neon Free and monitor free quota/credit use.

## Official sources reviewed (2026-11-03)

- [OSHA 1926.650, scope](https://www.osha.gov/laws-regs/regulations/standardnumber/1926/1926.650)
- [OSHA 1926.651, excavation requirements](https://www.osha.gov/laws-regs/regulations/standardnumber/1926/1926.651)
- [OSHA 1926.652, cave-in protection](https://www.osha.gov/laws-regs/regulations/standardnumber/1926/1926.652)
