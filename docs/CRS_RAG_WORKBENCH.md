# CRS-RAG Research Workbench

**Status: research implementation, not a certified compliance product.** The existing
deterministic CRS API remains unchanged. The browser workbench uses separate
session-authenticated endpoints and stores model proposals separately.

## Capabilities

1. Submit natural-language excavation scenarios at the /research web interface.
2. Extract user-reported conditions with a limited local parser or an optional LLM.
3. Maintain versioned structured state in the existing Python/PostgreSQL CRS engine.
4. Retrieve actual text passages from copies of official OSHA 29 CFR 1926.650,
   1926.651, 1926.652 and Subpart P Appendices A-F.
5. Generate citation-grounded, human-review-required candidate assessments when
   an approved model is configured. Reject citations not found in retrieved passages.
6. Store proposed condition-to-decision dependencies in separate database tables.
   On changes, invalidate affected candidate decisions and selectively reevaluate.
7. Support hypothetical branches, case history and scenario follow-ups.
8. View all these components, OSHA evidence and structured assessments through
   the protected browser workspace.

## Trust boundaries and limitations

- The model is not a source of regulatory authority. Never treat its output as
  OSHA clearance, engineering approval, or confirmation that an excavation is safe.
- Retrieved evidence IDs must exactly match indexed official OSHA document chunks.
  Unknown references are rejected; all LLM output needs expert verification.
- User reports are assertions, not verified field evidence.
- The existing deterministic engine assesses only six narrow OSHA requirements
  plus a summary. It does not check every requirement in the source documents.
- The model's new dependencies are proposed and unreviewed. They may be incomplete.
- Source indexing preserves textual HTML, not all appendix drawings, graphics and
  table layout. Review the original OSHA links for technical drawings.
- The corpus is an explicitly downloaded timestamped snapshot. It is not a live
  regulatory update service, and state-plan requirements may differ.
- Retrieval uses BM25 sparse text search against downloaded source passages.
  An optional grounded LLM makes this RAG. Dense vector search is not yet included.
- The workspace is shared behind an administrator password. It does not yet offer
  production multi-user identity, tenancy, access logs or rate limiting.
- Do not send sensitive construction field, student, or personal information
  without approved research privacy and data handling arrangements.
- The EX-01 ground-truth spreadsheet remains private and is not in this public repo.

## Safe deployment to the existing Azure Container App

The CI suite exercises all existing CRS behavior and the new workbench. Keep the
currently running Azure image unchanged until the feature branch passes CI and
has been reviewed.

After merging PR #7, GitHub Actions publishes a new immutable image.
In the Azure Portal, create these Container App secrets under the existing
resource group rg-siteobserver-reu / app construction-edu-demo:

- crs-web-password: unique random research web password, at least 16 characters.
- crs-web-session-secret: random signing secret, at least 32 characters.

Keep the existing crs-postgres-url and crs-api-key secrets. In Azure Cloud Shell
PowerShell, configure secret references only:

~~~powershell
az containerapp update --name construction-edu-demo --resource-group rg-siteobserver-reu --set-env-vars CRS_WEB_PASSWORD=secretref:crs-web-password CRS_WEB_SESSION_SECRET=secretref:crs-web-session-secret CRS_REQUIRE_DURABLE_DB=1
~~~

Deploy the validated container image using the GitHub SHA, not an unreviewed
branch or mutable latest tag. Open the existing app's /research page and sign
in with the new research password. Ingest the official source sections from
the document library controls before enabling model-assisted assessments.

### Optional Azure Foundry model

Configure only after verifying budget, subscription eligibility, privacy and
supervisor approval:

- CRS_LLM_BASE_URL: approved HTTPS API root ending in /openai/v1.
- CRS_LLM_MODEL: exact deployment model name.
- CRS_LLM_API_KEY: Azure Container App secret reference, never frontend code.

Example: https://YOUR-RESOURCE.openai.azure.com/openai/v1

The gateway calls the documented chat-completions endpoint and requires
JSON-object structured responses. Model versions that do not support JSON mode
must be adapted deliberately. No paid service is automatically provisioned.

Without the model, the workbench still provides deterministic rule checks,
limited English corrections, history, hypothetical branches and OSHA search.

### Developer verification

~~~bash
python -m pip install Flask==3.1.1 pytest 'psycopg[binary]>=3.2,<4'
python -m pytest -q construction-edu-flask/test_workbench.py
python -m pytest -q construction-edu-flask/test_crs.py construction-edu-flask/test_nl_pipeline.py
~~~

For non-TLS localhost only, setting CRS_WEB_INSECURE_LOCAL=1 permits local
cookie testing. Production cookies are Secure, HttpOnly and SameSite=Strict.
State-changing workbench endpoints require session auth and CSRF validation.

### Workbench routes

- POST /api/workbench/login, GET /api/workbench/session, POST /api/workbench/logout
- GET /api/workbench/status
- POST /api/workbench/ingest and POST /api/workbench/search
- POST /api/workbench/scenarios
- GET /api/workbench/scenarios/<id>?branch=base
- POST /api/workbench/scenarios/<id>/messages with expected_version
- POST /api/workbench/scenarios/<id>/branches

The existing /api/crs/... routes remain behind the original bearer key.

## Research validation requirements

Use the private EX-01 15-turn dialogue workbook to assess source-grounding and
correctness. Evaluate uncertain witness statements, shield removal and
relocation, hypothetical branches, explicit corrections, soil and excavation
depth changes, and conflicting reports.

Report condition extraction accuracy, citation recall@k, candidate-dependency
precision and recall, selective-versus-full recomputation parity, latency,
model cost and unsafe unsupported assertions. The tests currently validate
integration mechanics; they are not a complete expert-labeled benchmark.

## Official OSHA sources

- https://www.osha.gov/laws-regs/regulations/standardnumber/1926/1926SubpartP
- https://www.osha.gov/laws-regs/regulations/standardnumber/1926/1926.650
- https://www.osha.gov/laws-regs/regulations/standardnumber/1926/1926.651
- https://www.osha.gov/laws-regs/regulations/standardnumber/1926/1926.652

Document ingestion stores text, SHA-256 source fingerprints and ingestion times
in the research database. Users should consult the linked authoritative sources
and have a qualified professional review any safety-related assessment.
