# CRS-RAG milestone: English scenario and correction API

This is the first integration step beyond the working structured-JSON CRS engine. The existing Flask website, state storage, rule decisions, and reverse dependency index are **not replaced**. The new \`crs/\` modules accept narrow English statements and forward extracted fields to the previously tested engine. No LLM API or extra Azure service is required.

**Research-only**: extraction is deterministic and incomplete; the current engine covers four curated OSHA excavation checks, not full occupational-safety compliance. Never rely on this prototype for actual worksite decisions.

## What this branch adds

- \`crs/extractor.py\`: conservative condition extraction with evidence snippets, numeric depths (feet/inches), trench type, worker exposure, protective system statements, limited egress, spoils, inspections and rain-event phrases. Unmentioned conditions remain unknown.
- \`crs/state_resolver.py\`: explicit natural-language create/revise operations; requires \`expected_version\` for corrections and blocks an explicit hypothetical from silently overwriting the base branch.
- \`crs/pipeline.py\`: small adapter facade.
- Authenticated Flask endpoints (same backend \`CRS_API_KEY\` as existing \`/api/crs/*\` endpoints).
- Regression tests for extraction, SQLite-backed end-to-end state revisions, selective reassessment, missing/contradictory facts, stale versions, and Flask authorization. Existing PostgreSQL CI tests remain in place.
- Dockerfile includes \`crs/\` to make the new Python package importable.

## Quick API check

Run locally with your own **backend-only** API key, or run against a deliberately deployed revision in Azure. Do not share or commit the API key, and do not put it in public JavaScript.

### Create an English scenario

\`\`\`http
POST /api/crs/nl/scenarios
Authorization: Bearer <server-side-api-key>
Content-Type: application/json

{"text":"Workers are inside a 6-foot trench without a protective system."}
\`\`\`

Sample response shape:

\`\`\`json
{
  "extraction": {
    "conditions": {
      "employees_exposed": true,
      "is_trench": true,
      "depth_ft": 6.0,
      "protective_system": "none"
    },
    "evidence": {"depth_ft": ["6-foot trench"]},
    "parser": "deterministic-excavation-v1",
    "limitations": "Only recognized explicit claims are extracted; missing facts remain unknown."
  },
  "scenario": {
    "scenario_id": "<generated-id>",
    "version": 1,
    "conditions": {},
    "decisions": []
  }
}
\`\`\`

The \`scenario.conditions\` and \`scenario.decisions\` keys above are abbreviated: the real response contains the full state snapshot and rule evaluations.

### Revise it using English

\`\`\`http
POST /api/crs/nl/scenarios/<scenario_id>/messages
Authorization: Bearer <server-side-api-key>
Content-Type: application/json

{"text":"Actually, the trench is only 4 feet deep.", "expected_version":1}
\`\`\`

The response contains \`extraction\` and the new \`scenario\`. The \`scenario.reassessed_decisions\` list should be \`assessed_rules_summary\`, \`protective_system\`, \`trench_egress\` while \`inspection\` and \`spoils\` remain unchanged, provided only depth changed.

### State and history retrieval

Use the existing protected routes:
- \`GET /api/crs/scenarios/<scenario_id>\`
- \`GET /api/crs/scenarios/<scenario_id>/history\`
- \`POST /api/crs/scenarios/<scenario_id>/branches\` with a named branch for hypothesis testing

## Run tests locally

\`\`\`bash
python -m pip install Flask==3.1.1 pytest
python -m pytest -q construction-edu-flask/test_app.py construction-edu-flask/test_crs.py construction-edu-flask/test_nl_pipeline.py
\`\`\`

The repository GitHub Actions workflow additionally runs the PostgreSQL tests in a local service container. It does not require Neon credentials in GitHub Actions.

## Current limitations and next research milestones

1. These patterns do **not** understand arbitrary English, references spanning many turns, negation in all forms, or all OSHA concepts. All extracted facts come from user statements and remain unverified. A significant next step is a benchmark of sentence-level extraction against hand-labeled examples, adding an LLM or semantic parser only after a baseline is measured.
2. The OSHA rules in \`crs_engine.py\` are **curated** with citations. No automated retrieval, version/change detection, semantic matching, or regulatory expert verification has been added yet. Next: a versioned OSHA corpus and deterministic/semantic retrieval linked to each decision.
3. The current site is still the separate demonstration frontend. Do not leak \`CRS_API_KEY\` into client-side JavaScript to link it to these endpoints. Build proper end-user authentication or a server-side session before making a public interactive editor.
4. Prepare labeled scenario corrections and measure extraction accuracy, decision validity, dependency invalidation precision/recall, and the number and latency of recomputations against full reassessment.
5. Keep cloud usage within Neon Free and Azure Container Apps Consumption free allocations. This branch does not deploy to Azure by itself.
