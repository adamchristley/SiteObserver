# Azure research results: SiteObserver milestone 1

> Last updated: 2026-10-13. All observed numbers below come from successful deployment and locally executed PowerShell commands. Unmeasured items remain explicitly marked **not measured**.

**Experiment date:** 2026-10-13  
**Subscription type:** Azure for Students (Michigan Technological University)  
**Azure region:** North Central US (`northcentralus`)  
**Resource group:** `rg-siteobserver-reu` (resource group metadata located in East US 2; the application is in North Central US)  
**Container Apps environment:** `env-siteobserver-reu`  
**App name:** `siteobserver-api`  
**Public URL:** https://siteobserver-api.graydesert-cb959016.northcentralus.azurecontainerapps.io  
**Published container:** `ghcr.io/adamchristley/siteobserver-api:latest`  
**GitHub revision at publishing:** `2cae0d79e244bd0b6d08f5a75c902d51284bc9fd` (use an immutable SHA tag in later reproductions)  
**Configuration:** ConsumptionOnly, 0.5 vCPU, 1 GiB RAM, minimum replicas 0, maximum replicas 1, external HTTPS ingress on container port 8000, no Log Analytics destination.

## Objective

Deploy and verify a containerized Python/FastAPI research simulator with Azure Container Apps, then characterize warm HTTP endpoint latency. The application is a **synthetic construction-site simulator**, not a validated predictive ML or workplace safety system.

## Deployment evidence (verified)

| Observation | Actual result |
| --- | --- |
| GitHub Container Registry image publication | [Publish API image: success](https://github.com/adamchristley/SiteObserver/actions/runs/38415096902) |
| GitHub CI after merge | [CI: success](https://github.com/adamchristley/SiteObserver/actions/runs/38415096986) |
| Container Apps environment | `provisioningState: Succeeded`, `location: North Central US` |
| Container App | `provisioningState: Succeeded`, `runningStatus: Running` |
| `GET /health` | HTTP request returned `status: ok`, `mode: simulation` |
| `GET /api/site` | Returned site `research-site-01`, 4 workers, 2 active equipment entries, 3 simulated hazard events in the sampled response |
| `GET /api/vision/status` | HTTP 404, confirming the experimental vision route is not published with the simulation-only configuration |

## HTTP performance data: warm sequential requests

PowerShell on a Windows machine executed **3 warm-up requests** and then **20 sequential timed requests** to the public `/health` endpoint using `Invoke-RestMethod` and `Measure-Command`. Requests were made from the user's workstation; these are **client-observed end-to-end times**, including HTTP/network/client overhead, not isolated cloud-side computation or inference latency.

| Measurement | Measured value |
| --- | ---: |
| Requests in sample | 20 |
| Successful / failed | 20 / 0 |
| Mean latency | 30.4265 ms (30.43 ms rounded) |
| Median latency | 29.87 ms |
| Minimum latency | 27.16 ms |
| Maximum latency | 34.43 ms |
| Standard deviation (sample) | ~1.91 ms |
| First request after idle (cold-start candidate) | **Not measured** |
| Local baseline | **Not measured** |
| Concurrent request throughput | **Not measured** |

Raw sample: [`azure-latency-2026-10-13.csv`](azure-latency-2026-10-13.csv).

**Limitations:** Small single-client warm sample only; no load testing, cross-region comparison, startup benchmark or repeated-day replication. Do not generalize this to production SLA or heavy traffic.

## Azure platform metrics (pending)

| Metric | Actual observed value |
| --- | --- |
| Azure Monitor request count | Not measured |
| CPU utilization/usage | Not measured |
| Memory working set | Not measured |
| Replica count over idle/active periods | Not measured |
| Actual Cost Management spend / credits | Not measured |
| Cost observation window | Not measured |

**Do not claim the deployment was free** until the subscription's Cost Management or student credit ledger confirms it. Scale-to-zero and excluded Log Analytics were selected to reduce exposure, but usage can still consume available credits.

## Engineering challenges and resolutions

1. **Regional policy restriction:** Creating the environment in `eastus2` failed with `RequestDisallowedByAzure`. The subscription's inherited `sys.regionrestriction` policy allowed `switzerlandnorth`, `belgiumcentral`, `spaincentral`, `northcentralus`, and `norwayeast`. Retrying the environment in `northcentralus` succeeded.
2. **Container build:** Used GitHub Actions and GHCR to build and publish from existing `backend/Dockerfile` instead of requiring a local Docker setup or a paid Azure Container Registry.
3. **Cloud-specific exposure:** Enabled `SITEOBSERVER_SIMULATION_ONLY=1`. An HTTP 404 from `/api/vision/status` verified that the experimental route is unavailable externally.
4. **Startup and scaling:** Configured 0 to 1 replicas, but no observed scale-to-zero/cold-start measurement yet.

## Results and next steps

**Demonstrated:** Azure CLI provisioning, region-policy troubleshooting, container deployment, public HTTPS API verification, GitHub-built image publication, and 20-request warm latency measurement.

**Still to collect:** Azure Monitor metrics, cloud credit/billing observation, idle/cold-start latency, optional local-vs-cloud comparison. A React frontend, construction-specific ML and validated risk prediction are **not** part of this first Azure infrastructure experiment.

**Screenshots:** Azure Container App overview, successful API response, Azure Monitor request/CPU/memory/replica charts, student credit/Cost Management usage.

**Cleanup:** Resource group still reported as in use at end of experiment; verify cleanup status and delete only when the research measurements are complete.
