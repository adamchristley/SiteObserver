# CRS-RAG Decision Dependency Tracking: Excavation Safety Prototype

**Purpose:** An executable research proof of concept extending the advisor's five-layer CRS-RAG proposal with explicit dependency tracking, selective reassessment, and hypothetical branches. **It is not a regulatory compliance certification, legal advice, safety approval, or a field-use tool.** The rule coverage is intentionally narrow and relies on user-asserted facts.

## What has been implemented

| Research layer | MVP support | Still needed |
|---|---|---|
| 1. State Extraction | Validated structured JSON fields, ADD/REVISE/BRANCH operations | Multi-turn natural-language/LLM extraction and RETURN intent |
| 2. CRS Management | SQLite state registry, versions, superseded states, audit history, named hypothetical branches | Shared durable cloud database, task expiration, conflict workflows |
| 3. State Resolution | Isolated base/hypothetical snapshots and version-aware retrieval | Rich persistent/task scope resolution and unresolved-conflict handling |
| 4. OSHA Retrieval | Four curated rule units with official OSHA source URLs and rule IDs | Full OSHA corpus ingestion, chunking, semantic retrieval, rule versioning |
| 5. Structured Assessment | Deterministic rule-specific findings with status, rationale, state evidence IDs, rule citations, evaluation count | LLM-supported assessment, exhaustive claim validation, human expert review |
| New Dependency Tracker | Relational reverse condition/regulation/decision dependency links, transitive affected-decision traversal, selective recomputation | Dynamic rule updates, generalized multi-decision DAG / knowledge-graph support |

Key distinction: changes to an excavation depth only re-run `protective_system`, `trench_egress`, and their dependent `assessed_rules_summary`. The unaffected `inspection` and `spoils` decisions retain their prior `evaluation_count` and `evaluated_version`.

## OSHA sources (official)

- [29 CFR 1926.652(a)(1), protective systems and stable-rock/<5 ft exceptions](https://www.osha.gov/laws-regs/regulations/standardnumber/1926/1926.652)
- [29 CFR 1926.651(c)(2), trench egress for >=4 ft, max 25 ft lateral travel](https://www.osha.gov/laws-regs/regulations/standardnumber/1926/1926.651)
- [29 CFR 1926.651(j)(2), spoils >=2 ft or adequate retaining devices](https://www.osha.gov/laws-regs/regulations/standardnumber/1926/1926.651)
- [29 CFR 1926.651(k)(1), competent-person inspections before work and after rain/hazard events](https://www.osha.gov/laws-regs/regulations/standardnumber/1926/1926.651)

Rules were curated against OSHA official pages on November 2, 2026. The system does **not** automatically update when OSHA rules or interpretations change. State outputs are preliminary evidence-based assessments of *only these four checks*. OSHA-approved state plans, other applicable requirements, site conditions, and engineering evaluations may change any real-world conclusion.

## Files to copy into your SiteObserver repo

Unzip this patch over the root of your existing `SiteObserver` repository (do not delete the existing `prompt-web/` directory):

- `construction-edu-flask/crs_engine.py` (new)
- `construction-edu-flask/app.py` (replace)
- `construction-edu-flask/Dockerfile` (replace)
- `construction-edu-flask/test_crs.py` (new)
- `construction-edu-flask/demo_crs.py` (new)
- `.github/workflows/publish-construction-edu.yml` (replace with updated test command)

Your existing `test_app.py`, existing `prompt-web/` files, and current public site can stay as they are. This patch does not connect an AI model. The current website will continue displaying the original demo until a new image is built and deliberately deployed.

## Run the proof-of-concept first, without deploying

In PowerShell from your SiteObserver repository root:

```powershell
python -m pip install Flask==3.1.1 pytest
python construction-edu-flask/demo_crs.py
python -m pytest -q construction-edu-flask/test_crs.py construction-edu-flask/test_app.py
```

## Try the Flask research API locally

The new research endpoints require a backend-only secret before they can be enabled. **Never put this key in frontend JavaScript or commit it to GitHub.**

```powershell
$env:CRS_API_KEY = "choose-a-long-local-dev-secret"
$env:CRS_DB_PATH = "$PWD\crs-local.sqlite3"
python -m flask --app construction-edu-flask/app.py run --port 8000
```

From a second PowerShell terminal:

```powershell
$headers = @{ Authorization = "Bearer choose-a-long-local-dev-secret" }
$body = @{ conditions = @{
  employees_exposed = $true
  depth_ft = 6
  stable_rock = $false
  protective_system = "none"
  competent_person_no_cave_in = $false
  is_trench = $true
  safe_egress_within_25ft = $true
  spoil_hazard = $true
  spoil_distance_ft = 3
  spoil_retained = $false
  inspection_before_work = $true
  rain_event = $false
}} | ConvertTo-Json -Depth 5
$scenario = Invoke-RestMethod -Method Post -Uri "http://127.0.0.1:8000/api/crs/scenarios" -Headers $headers -ContentType 'application/json' -Body $body
$scenario.decisions | Select-Object decision_id,status,evaluation_count

$sid = $scenario.scenario_id
$patch = @{changes = @{depth_ft = 4}; expected_version = 1} | ConvertTo-Json -Depth 4
$updated = Invoke-RestMethod -Method Patch -Uri "http://127.0.0.1:8000/api/crs/scenarios/$sid/conditions" -Headers $headers -ContentType 'application/json' -Body $patch
$updated.reassessed_decisions
$updated.unchanged_decisions
```

Other endpoints:

- `GET /api/crs/regulations`: official source references and condition dependencies
- `GET /api/crs/scenarios/{id}?branch=base`: resolved state, current decisions, evidence IDs
- `POST /api/crs/scenarios/{id}/branches` with `{"name":"what_if"}`: fork scenario
- `PATCH /api/crs/scenarios/{id}/conditions` with `{"branch":"what_if","changes":{"depth_ft":4}}`: revise the hypothetical branch
- `GET /api/crs/scenarios/{id}/history?branch=base`: state events and decision transitions

## Deployment warning

SQLite at `/tmp/crs_rag_research.sqlite3` is **ephemeral** inside Azure Container Apps. Scale-to-zero, restarts, and multiple replicas make it unsuitable for persistent multi-user research data. To deploy the tracking feature, first move the repository of states/events/dependencies to a durable managed database, add proper authentication and access control, and confirm security and OSHA source review. Until then, leave `CRS_API_KEY` unset in Azure so research CRUD endpoints remain disabled. Do **not** send personal, student, or operationally sensitive field data into this experimental system.

## Proposed experiment for Xiaoyu

1. Create a fixed excavation scenario with four OSHA checks plus the aggregate assessment.
2. Apply one change at a time (depth, egress, spoils, or inspection) and record every state revision.
3. Verify the *affected-decision set* matches the reverse dependency graph, including decision-to-decision edges.
4. Compare final decisions with full recomputation and with a human-labeled evaluation set.
5. Measure reassessment precision/recall, decisions evaluated per turn, latency, and regulatory citation correctness.

## Research limitations

This is a deterministic benchmarkable skeleton, not the full CRS-RAG paper system. It does not ingest arbitrary conversational turns, perform embeddings/vector search, reason over all OSHA regulations, or connect Azure OpenAI. It does prove the new backend concept with actual versioned storage and dependency-driven selective recomputation rather than prompt instructions alone.
