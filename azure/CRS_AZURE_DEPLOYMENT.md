# Deploy CRS-RAG to Azure Container Apps with durable PostgreSQL

The live app is **construction-edu-demo** in resource group **rg-siteobserver-reu**. This repo builds and publishes a GHCR image after CI passes, but cannot change your Azure subscription without an authenticated Azure CLI session.

## 1. Deploy the tested backend safely

In **Azure Cloud Shell PowerShell** use the image published from the merge commit on main, NOT a branch or an unverified latest tag:

```powershell
az account show --query '{name:name,id:id}' -o table
az containerapp update --resource-group rg-siteobserver-reu --name construction-edu-demo --image ghcr.io/adamchristley/construction-edu-demo:<full-main-merge-SHA> --set-env-vars CRS_REQUIRE_DURABLE_DB=1
```

Or clone this repo in Cloud Shell and run `./azure/deploy-crs.ps1 -ImageTag <full-main-merge-SHA>`.

The existing public Prompt Lab continues to return a fixed acknowledgement. No natural-language OSHA assessment interface has been connected yet. With no API key configured, `/api/crs/*` returns HTTP 403 instead of exposing research data.

## 2. Provision durable database before enabling CRS research CRUD

The Python engine now supports **Azure Database for PostgreSQL Flexible Server** via the environment variable `CRS_DATABASE_URL`. Existing local SQLite tests continue to work, but SQLite inside the Container App is ephemeral. When `CRS_REQUIRE_DURABLE_DB=1`, the protected API refuses to run with only SQLite.

In the Azure Portal, create a PostgreSQL Flexible Server in a location and SKU permitted by the Azure for Students subscription. Use private networking reachable by the Container Apps environment, TLS, and an app-specific database user. Check pricing and student-credit eligibility before provisioning. **Do not open database access to the public Internet or enable an unrestricted Azure-services firewall rule** for a quick demo.

The prototype creates its tables and indexes when it connects. The initial DB user must have sufficient schema permissions. For a hardened deployment, use a separate migration identity and restrict the runtime user to DML.

In the existing Container App, under **Settings > Secrets**, create:

- `crs-postgres-url`: `postgresql://USER:URL_ENCODED_PASSWORD@SERVER.postgres.database.azure.com:5432/DB_NAME?sslmode=require`
- `crs-api-key`: a long random research-only API bearer token

Never commit credentials, enter them into the public Prompt Lab, or paste them into chat. Set up the secret values directly in the Azure Portal rather than putting them in command-line history.

Then in **Azure Cloud Shell PowerShell**, apply only references to secrets:

```powershell
az containerapp update --resource-group rg-siteobserver-reu --name construction-edu-demo --set-env-vars CRS_DATABASE_URL=secretref:crs-postgres-url CRS_API_KEY=secretref:crs-api-key CRS_REQUIRE_DURABLE_DB=1
```

A successful API response does not prove persistence until the same scenario survives a new revision/restart. Treat loss of DB connectivity as a failed deployment. The application must not silently fall back to SQLite.

## 3. Verify the backend

With a test API key held only in your local shell environment, use synthetic excavation data:

```powershell
$base = 'https://construction-edu-demo.graydesert-cb959016.northcentralus.azurecontainerapps.io'
$headers = @{ Authorization = "Bearer $env:CRS_TEST_KEY" }
$conditions = @{
  employees_exposed = $true
  depth_ft = 6
  stable_rock = $false
  protective_system = 'none'
  competent_person_no_cave_in = $false
  is_trench = $true
  safe_egress_within_25ft = $true
  spoil_hazard = $true
  spoil_distance_ft = 3
  spoil_retained = $false
  inspection_before_work = $true
  rain_event = $false
}
$body = @{conditions=$conditions} | ConvertTo-Json -Depth 5
$first = Invoke-RestMethod -Method Post "$base/api/crs/scenarios" -Headers $headers -ContentType 'application/json' -Body $body
$sid = $first.scenario_id
$patch = @{changes=@{depth_ft=4}; expected_version=1} | ConvertTo-Json -Depth 4
$changed = Invoke-RestMethod -Method Patch "$base/api/crs/scenarios/$sid/conditions" -Headers $headers -ContentType 'application/json' -Body $patch
$changed.reassessed_decisions
$changed.unchanged_decisions
```

Expected reassessed decisions: `assessed_rules_summary`, `protective_system`, `trench_egress`. Expected unchanged: `inspection`, `spoils`.

Confirm `GET /api/crs/scenarios/{id}` returns the same data after a new Container App revision. Use only synthetic data: this is a research proof of concept with four non-exhaustive OSHA rules, not a field safety decision tool.

## CI

GitHub Actions runs SQLite/Flask tests and an end-to-end test against an ephemeral PostgreSQL 16 service for PRs. The workflow builds/publishes images from merged main only if tests pass.
