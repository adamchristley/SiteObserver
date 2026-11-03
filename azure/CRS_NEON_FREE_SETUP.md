# CRS-RAG with Neon Free PostgreSQL + Azure Container Apps

This is the zero-new-Azure-database-cost route for testing Xiaoyu's excavation-safety decision dependency tracking prototype. **No paid database is needed.** Keep the existing Azure Container App `construction-edu-demo` and its currently deployed image. The backend already reads PostgreSQL connection URLs from `CRS_DATABASE_URL` and requires a bearer secret in `CRS_API_KEY`.

## Free-tier scope and costs

Neon Free (as announced October 2026): 1 GB storage and 100 compute-unit hours per project per month, with scale-to-zero after inactivity. Choose **Free**, not Launch/Scale, and verify current quotas in the console. Usage limits may suspend service. The existing Azure Container App has a separate Azure free-usage allowance; it **may still consume student credits** if that allowance is exceeded. Monitor Azure Cost Management. Never upgrade either service to a paid tier for this experiment.

## 1. Create the database

1. Visit https://console.neon.tech/ and sign in. Choose the **Free** plan.
2. Create a project called `crs-rag-research`. Choose a US region reasonably close to Azure North Central US.
3. In Neon click **Connect** for the `main` branch. Select a **direct/unpooled PostgreSQL connection string** for this low-concurrency prototype. Keep `sslmode=require`.
4. Neon displays a URL like `postgresql://ROLE:PASSWORD@HOST.neon.tech/neondb?sslmode=require`. **Treat it as a password.** Never paste the full URL into ChatGPT, GitHub, an issue, logs, screenshots, or a public frontend.

There is no requirement for an Azure PostgreSQL Flexible Server or a new VNet-connected Container Apps environment. Neon is reached via its public TLS-enabled PostgreSQL endpoint.

## 2. Save credentials as Azure Container App secrets

In https://portal.azure.com/ open **Container Apps > construction-edu-demo** (resource group `rg-siteobserver-reu`), then **Settings > Secrets** (or **Security > Secrets** depending on portal layout):

- Create secret **crs-postgres-url**, value = full Neon PostgreSQL connection URL copied from Neon.
- Create secret **crs-api-key**, value = a unique long randomly generated bearer key used only for this research backend.

Do not print or expose the values. A random 32-byte API key is sufficient for this prototype; a password manager can generate one. Store it privately because you will need it for API tests.

## 3. Connect the existing Container App

In **Azure Cloud Shell PowerShell**, run one line (no Bash backslashes):

```powershell
az containerapp update --resource-group rg-siteobserver-reu --name construction-edu-demo --set-env-vars CRS_DATABASE_URL=secretref:crs-postgres-url CRS_API_KEY=secretref:crs-api-key CRS_REQUIRE_DURABLE_DB=1
```

This creates a new Container App revision. The app may take a moment to connect after Neon's compute wakes up. The existing Prompt Lab is a *demo* interface and still only returns a fixed acknowledgment; the CRS API is available at `/api/crs/*` to callers who know the bearer key. **Never put this key in the browser JavaScript**; do not make a public self-service research API until user authentication/rate limiting is designed.

## 4. Verify that persisted decisions work

Verify health first:

```powershell
$base = 'https://construction-edu-demo.graydesert-cb959016.northcentralus.azurecontainerapps.io'
Invoke-RestMethod "$base/api/health"
```

For testing synthetic data with the secret, use Azure Cloud Shell PowerShell:

```powershell
$key = ConvertFrom-SecureString (Read-Host 'Enter research API key' -AsSecureString) -AsPlainText
$h = @{Authorization = "Bearer $key"}
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
$created = Invoke-RestMethod -Method Post "$base/api/crs/scenarios" -Headers $h -ContentType 'application/json' -Body (@{conditions=$conditions} | ConvertTo-Json -Depth 6)
$sid = $created.scenario_id
$revised = Invoke-RestMethod -Method Patch "$base/api/crs/scenarios/$sid/conditions" -Headers $h -ContentType 'application/json' -Body (@{changes=@{depth_ft=4};expected_version=1} | ConvertTo-Json -Depth 5)
$revised.reassessed_decisions
$revised.unchanged_decisions
$persisted = Invoke-RestMethod "$base/api/crs/scenarios/$sid" -Headers $h
$persisted.version
Remove-Variable key
```

Expected reassessed decision IDs are `assessed_rules_summary`, `protective_system`, `trench_egress`; `spoils` and `inspection` should remain unchanged. Check that `$persisted.version` is 2 and that the same scenario remains after a Container App restart. This is a narrow research demo, **not a comprehensive OSHA or worksite safety determination**.

## 5. Monitor cost

- Neon: Project > Usage; stay within 100 CU-hours and 1 GB; Free plan, no paid upgrades.
- Azure: Cost Management > Cost analysis and budgets; check Container Apps free allowance and student-credit usage.
- Avoid polling protected endpoints in a continuous loop: this wakes the database and consumes free compute.

## What remains for Xiaoyu's research

This proves versioned facts, OSHA-referenced deterministic decisions, dependency edges, and selective reassessment. It does **not** yet provide multi-turn natural-language extraction, semantic OSHA retrieval, comprehensive regulatory validation, or a user-facing CRS-specific decision visualization. Those are subsequent research milestones.
