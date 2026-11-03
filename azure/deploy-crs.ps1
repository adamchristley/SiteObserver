# Run in Azure Cloud Shell PowerShell after the merged GitHub image build passes.
# Example: ./azure/deploy-crs.ps1 -ImageTag <full-main-commit-sha>
param([Parameter(Mandatory=$true)][string]$ImageTag)
$ErrorActionPreference = 'Stop'
$rg = 'rg-siteobserver-reu'
$app = 'construction-edu-demo'
$image = "ghcr.io/adamchristley/construction-edu-demo:$ImageTag"
Write-Host 'Selected Azure subscription:'
az account show --query '{name:name,id:id}' -o table
Write-Host 'Verifying target app exists...'
az containerapp show --resource-group $rg --name $app --query 'properties.provisioningState' -o tsv
if ($LASTEXITCODE -ne 0) { throw 'Target app not found. Deployment stopped.' }
Write-Host "Deploying $image. Research API stays protected."
az containerapp update --resource-group $rg --name $app --image $image --set-env-vars CRS_REQUIRE_DURABLE_DB=1 -o table
if ($LASTEXITCODE -ne 0) { throw 'Container App update failed.' }
$fqdn = az containerapp show --resource-group $rg --name $app --query 'properties.configuration.ingress.fqdn' -o tsv
if ($LASTEXITCODE -ne 0 -or -not $fqdn) { throw 'Could not get website hostname.' }
$base = "https://$fqdn"
Write-Host "Checking $base/api/health"
Invoke-RestMethod "$base/api/health" | ConvertTo-Json
Write-Host 'For research CRUD, provision PostgreSQL and configure secret references.'
