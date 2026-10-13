# Azure milestone 1: deploy the SiteObserver simulator API

**Goal:** Document a real deployment, measure response times, and inspect Azure platform metrics. This milestone does not require YOLO, a GPU, or the React dashboard.

The deployment uses:
- GitHub Actions to build and publish a Docker image to GitHub Container Registry (GHCR).
- Azure Container Apps on the **Consumption** plan, scale-to-zero (0 to 1 replicas).
- No Azure Container Registry (ACR).
- No Log Analytics workspace. The environment is configured with `--logs-destination none`. Azure platform metrics remain available, but durable application logs are intentionally omitted.

**Important:** Azure resources may incur charges despite free grants. Use an eligible Azure for Students subscription with unspent credits or check pricing and billing restrictions before provisioning. This guide creates resources only when you run its commands. A budget alert is NOT a hard spending limit. Delete the entire resource group when the experiment ends.

## 1. Publish the container image

After merging the associated PR, open **GitHub > SiteObserver > Actions > Publish API image > Run workflow**, or let the workflow run automatically on a backend push to `main`.

Image name: `ghcr.io/adamchristley/siteobserver-api:latest`.

If the image package is private, go to your GitHub profile > Packages > siteobserver-api > Package settings > Change visibility > Public. **Making a package public is an irreversible visibility change**; only proceed for this repository's non-confidential demonstration image. You can instead choose a private registry approach, which requires authentication and a different setup.

## 2. Inspect the Azure subscription (Windows PowerShell)

Install Azure CLI if necessary: https://learn.microsoft.com/cli/azure/install-azure-cli-windows

```powershell
az login
az account list --output table
# Explicitly select the Azure for Students subscription if you have it:
az account set --subscription "<YOUR-SUBSCRIPTION-ID>"
az account show --query "{name:name,id:id,state:state}" --output table
az extension add --name containerapp --upgrade
```

Before the next step, confirm the selected subscription, remaining student credit, and any relevant region/resource restrictions in the Azure portal. Never paste account tokens or subscription credentials into GitHub issues.

## 3. Create a minimal Container Apps environment

```powershell
$RG = "rg-siteobserver-reu"
$LOCATION = "eastus2"
$ENV = "env-siteobserver-reu"
$APP = "siteobserver-api"

az group create --name $RG --location $LOCATION

az containerapp env create `
  --name $ENV `
  --resource-group $RG `
  --location $LOCATION `
  --environment-mode ConsumptionOnly `
  --logs-destination none
```

If the student subscription does not permit `eastus2`, select a supported location. Do not enable dedicated workload profiles, paid networking options, or a Log Analytics workspace without reviewing their costs.

## 4. Deploy only the simulator

The `SITEOBSERVER_SIMULATION_ONLY=1` flag removes experimental video-upload and webcam endpoints from this publicly reachable version.

```powershell
az containerapp create `
  --name $APP `
  --resource-group $RG `
  --environment $ENV `
  --image ghcr.io/adamchristley/siteobserver-api:latest `
  --ingress external `
  --target-port 8000 `
  --cpu 0.5 `
  --memory 1.0Gi `
  --min-replicas 0 `
  --max-replicas 1 `
  --env-vars SITEOBSERVER_SIMULATION_ONLY=1

$fqdn = az containerapp show --name $APP --resource-group $RG --query "properties.configuration.ingress.fqdn" --output tsv
$baseUrl = "https://$fqdn"
Write-Host $baseUrl
Invoke-RestMethod "$baseUrl/health"
Invoke-RestMethod "$baseUrl/api/site"
```

Expected health JSON: `{"status":"ok","mode":"simulation"}`. **This is an expectation, not a recorded Azure result.**

If deployment fails to pull the image, verify the GHCR package is public and the workflow successfully published it. If the container starts but requests fail, inspect the app's revision state and port 8000.

## 5. Collect results

Run 10 warm requests and save your own latency observations:

```powershell
1..10 | ForEach-Object {
  $n = $_
  $ms = (Measure-Command { $null = Invoke-RestMethod "$baseUrl/health" }).TotalMilliseconds
  [pscustomobject]@{ Request = $n; LatencyMs = [math]::Round($ms, 1) }
} | Tee-Object -Variable timings | Format-Table
$timings | Export-Csv -Path "siteobserver-azure-latency.csv" -NoTypeInformation
```

Note the time of the first request after several minutes of no traffic separately as a **cold-start candidate**, not a guaranteed cold start. Use the Azure portal: **Container App > Monitoring > Metrics** to capture requests, CPU, memory and replica count if available on your subscription. Metric data can lag behind requests. Collect the same 10-request test locally for a non-identical but useful baseline. Record network location and that this is client-perceived HTTP latency, not server processing time.

Useful read-only CLI commands:

```powershell
az containerapp show --name $APP --resource-group $RG --query "{state:properties.provisioningState,host:properties.configuration.ingress.fqdn}" --output json
az containerapp revision list --name $APP --resource-group $RG --output table
az containerapp replica list --name $APP --resource-group $RG --revision "<REVISION-NAME>" --output table
```

Use `docs/azure-results.md` for the report, including Azure cost data taken from Cost Management, not an estimate.

## 6. Clean up immediately after capturing results

```powershell
# Review the resources before deletion:
az resource list --resource-group $RG --output table

# Irreversibly deletes all resources in this research resource group:
az group delete --name $RG --yes
```

Do not delete a resource group that contains other work. Verify its contents first.

## Follow-up milestone

Connect the React dashboard using Azure Static Web Apps, with an explicit CORS origin for its host. Then measure requests and failures through Azure Monitor. Keep all ML inference local during the first cloud deployment.

## Official references

- https://learn.microsoft.com/en-us/azure/container-apps/billing
- https://learn.microsoft.com/en-us/cli/azure/containerapp/env
- https://learn.microsoft.com/en-us/cli/azure/containerapp
- https://docs.github.com/en/packages/working-with-a-github-packages-registry/working-with-the-container-registry
