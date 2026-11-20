# CRS-RAG research platform: implementation and Azure rollout

## Purpose and safety boundaries

This extends the five-layer CRS-RAG excavation prototype with official source-document retrieval, optional LLM grounding, a browser workspace, proposed condition-to-decision links, and an evaluation harness. It is not a field OSHA compliance service or a substitute for a competent person, engineer, or expert review.

The existing CRS engine remains the source of truth for the six deterministic checks and their aggregate summary. Relevant citations are not by themselves legal applicability or compliance findings.

## Architecture

1. Researcher enters the web workspace password. Flask issues an HTTP-only, Secure, SameSite=Strict signed session cookie with CSRF protection. The browser never receives the backend API bearer key.
2. The user enters a scenario, correction, or question, optionally on a hypothetical branch. The POST /api/crs/assistant route processes the message.
3. The offline document retriever searches an archived official regulatory snapshot, with source citations and immutable hashes. When OSHA blocks automated requests, the build downloads the official GovInfo eCFR Title 29 bulk XML archive and indexes the relevant excavation rules and appendices.
4. If Azure OpenAI is configured, the model proposes only explicitly asserted condition facts, conflicts, grounded citations, new decision candidates and dependencies. Unknown fields, unsupported statuses and ungrounded citations are rejected. If the model is unavailable, the fallback is explicitly labeled deterministic.
5. The Python/PostgreSQL core persists versioned facts, history, branches, decision evidence, and predefined dependency-driven reassessment.
6. LLM candidates and edges are separately persisted. A changed condition invalidates affected model proposals, marks them for human review, and selectively updates affected candidate decision evaluations. Model proposals never silently alter the deterministic OSHA rule definitions.
7. The site displays research analyses, source passages, deterministic decisions, candidate decisions, version histories, and both types of dependency edges.

## Sources

- OSHA 29 CFR 1926.650, 1926.651 and 1926.652.
- OSHA Subpart P Appendices A through F.
- https://www.osha.gov/laws-regs/regulations/standardnumber/1926/1926subpartp
- https://www.govinfo.gov/bulkdata/ECFR/title-29/ECFR-title29.xml

Docker build creates /app/crs/data/osha_corpus.json and records source references, a retrieval timestamp, archive/content fingerprints, citations and individual paragraph hashes. A GitHub Actions smoke build fetched nine source pages and 163 chunks. The archive is a point-in-time snapshot, not continuously refreshed. Document ranking is BM25 lexical, not embeddings/vector similarity. The LLM can be grounded on retrieved source-text passages.

Manual source refresh, from inside construction-edu-flask:

    python -m pip install beautifulsoup4==4.13.4
    python -m crs.document_rag --output crs/data/osha_corpus.json

Only fixed US government source URLs are used. Runtime API requests never perform document downloads.

## API

All CRS research endpoints require private Authorization Bearer credentials or an authenticated browser session with CSRF on mutating requests:

- POST /api/crs/assistant: JSON keys text, optional scenario_id, branch, expected_version.
- GET /api/crs/assistant/status: corpus availability and model configuration, without secrets.
- GET /api/crs/assistant/{scenario_id}/graph: condition dependencies and model candidate decisions.
- GET /api/crs/assistant/{scenario_id}/history: research turn history.
- The existing scenario, version, hypothetical branch and curated OSHA API routes remain compatible.
- POST /api/crs/web/login, GET /api/crs/web/session, POST /api/crs/web/logout: signed research sessions.

The shared-password preview is intended for a trusted research team. Before any external production deployment add an identity provider, per-user authorization, distributed rate limits, audit controls and a security review.

## Tests

From the repository root:

    python -m pip install Flask==3.1.1 pytest beautifulsoup4==4.13.4 'psycopg[binary]>=3.2,<4'
    python -m pytest -q construction-edu-flask/test_app.py construction-edu-flask/test_crs.py construction-edu-flask/test_nl_pipeline.py construction-edu-flask/test_osha_retrieval.py construction-edu-flask/test_layer5_hazards.py construction-edu-flask/test_crs_platform.py
    docker build -f construction-edu-flask/Dockerfile -t siteobserver-crs-rag .

GitHub Actions additionally runs PostgreSQL integration against a disposable database. The Docker smoke test verifies that source ingestion and packaging work before an image can be published.

## EX-01 ground truth evaluation

The supplied 15-turn workbook is a separate research input and should not be committed to the public repository without approval.

Retrieval-only analysis, with no paid model calls:

    python construction-edu-flask/evaluate_dialogues.py "C:\path\to\EX-01_15_Dialogues_Ground_Truth.xlsx" --output ex01-retrieval.json

The output includes per-turn citation-section recall and latency. With Azure OpenAI credentials deliberately configured, add --live and --confirm-model-billing for a metered test run. Ground-truth status labels remain intact and are not treated as field-work authorization.

## Azure rollout after successful review and CI

Verified Azure resources: rg-siteobserver-reu, env-siteobserver-reu, and construction-edu-demo in North Central US. Existing settings CRS_DATABASE_URL, CRS_API_KEY and CRS_REQUIRE_DURABLE_DB=1 must be retained.

1. In Azure Portal, add two new strong secrets on the Container App: crs-web-password and crs-web-session-key. The latter should be at least 32 random bytes. Store both values in a password manager, never in browser JavaScript or GitHub.
2. After the reviewed PR is merged, verify that the GHCR publish job succeeds for the resulting main-branch commit. Use that exact SHA tag, not a guessed or unverified latest.
3. In Azure Cloud Shell PowerShell run:

    $rg = "rg-siteobserver-reu"
    $app = "construction-edu-demo"
    $image = "ghcr.io/adamchristley/construction-edu-demo:<FULL-MAIN-COMMIT-SHA>"
    az containerapp update --resource-group $rg --name $app --image $image
    az containerapp update --resource-group $rg --name $app --set-env-vars CRS_WEB_PASSWORD=secretref:crs-web-password CRS_WEB_SESSION_KEY=secretref:crs-web-session-key

4. If an approved Azure OpenAI chat deployment exists, add a new Container App secret named crs-azure-openai-key via the Azure Portal, then configure:

    az containerapp update --resource-group $rg --name $app --set-env-vars AZURE_OPENAI_ENDPOINT=https://YOUR-RESOURCE.openai.azure.com AZURE_OPENAI_DEPLOYMENT=YOUR-DEPLOYMENT AZURE_OPENAI_API_KEY=secretref:crs-azure-openai-key

The code uses the Azure OpenAI v1 chat-completions endpoint. Having Azure Container Apps access does not establish that Azure OpenAI has been provisioned or that costs are approved. Model inference may be billed.

5. Check the running image, new revision, source corpus readiness and model mode via authenticated API status. Test only synthetic excavation scenarios. Confirm records persist after a restart. Roll back to the previous known-good Container App revision if any smoke test fails.

## Remaining research/production limitations

- Independent expert-reviewed benchmarks and human-grounded evaluations are still necessary.
- Dependency edges generated by the LLM require human review and are not accepted as certified OSHA rules.
- Official regulatory updates require controlled corpus refresh, evidence version migration and invalidation.
- Evaluate vector/semantic retrieval against BM25. Vector embeddings are not shipped in this branch.
- Harden identity, user isolation, conflict handling, observability, and production security.
- No field safety performance or unrestricted OSHA compliance coverage has been validated.
