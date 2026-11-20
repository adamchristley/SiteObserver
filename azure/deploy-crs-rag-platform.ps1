# Run in authenticated Azure Cloud Shell PowerShell.
# Example: ./azure/deploy-crs-rag-platform.ps1 -ImageTag eccfbf9780174edb68e4835d5a712fe4ee9da954
param(
  [Parameter(Mandatory=$true)]
  [ValidatePattern('^[a-f0-9]{40}$')]
  [string]$ImageTag,
  [string]$ResourceGroup = 'rg-siteobserver-reu',
  [string]$AppName = 'construction-edu-demo'
)
$ErrorActionPreference = 'Stop'
$image = "ghcr.io/adamchristley/construction-edu-demo:$ImageTag"
$account = az account show --query '{name:name,state:state}' -o json | ConvertFrom-Json
if ($LASTEXITCODE -ne 0 -or $account.state -ne 'Enabled') { throw 'Azure subscription is not enabled.' }
$app = az containerapp show --resource-group $ResourceGroup --name $AppName -o json | ConvertFrom-Json
if ($LASTEXITCODE -ne 0 -or -not $app) { throw 'Existing Container App not accessible.' }
if ($app.properties.runningStatus -ne 'Running') { throw 'Current revision is not Running. Investigate before replacing.' }
$priorImage = $app.properties.template.containers[0].image
$priorRevision = $app.properties.latestReadyRevisionName
$names = @($app.properties.template.containers[0].env | ForEach-Object { $_.name })
foreach ($required in @('CRS_REQUIRE_DURABLE_DB','CRS_DATABASE_URL','CRS_API_KEY')) {
    if ($names -notcontains $required) { throw "Required setting $required is missing. Nothing deployed." }
}
Write-Host "Current image: $priorImage"
Write-Host "Current ready revision: $priorRevision"
Write-Host "Candidate image: $image"

# Synthetic scenario proves PostgreSQL persistence across the image revision.
$key = az containerapp secret show --name $AppName --resource-group $ResourceGroup --secret-name crs-api-key --query value -o tsv
if ($LASTEXITCODE -ne 0 -or -not $key) { throw 'Could not retrieve API key for persistence test.' }
$fqdn = $app.properties.configuration.ingress.fqdn
if (-not $fqdn) { throw 'Ingress hostname missing.' }
$base = "https://$fqdn"
$headers = @{ Authorization = "Bearer $key" }
$testInput = @{conditions=@{is_trench=$true;depth_ft=6;employees_exposed=$true}} | ConvertTo-Json -Depth 5
$created = Invoke-RestMethod "$base/api/crs/scenarios" -Method POST -Headers $headers -ContentType 'application/json' -Body $testInput -TimeoutSec 60
$sid = $created.scenario_id
if (-not $sid -or $created.version -ne 1) { throw 'Predeployment database test failed.' }
Write-Host 'Predeployment synthetic scenario stored.'

# Web session secrets. No literal password is entered into shell history or GitHub.
$passwordSecure = Read-Host 'Choose a new research web password (16+ characters)' -AsSecureString
$ptr = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($passwordSecure)
try { $password = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($ptr) }
finally { [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($ptr) }
if (-not $password -or $password.Length -lt 16) { throw 'Web password must be at least 16 characters. Nothing deployed.' }
$sessionSecret = [Convert]::ToBase64String([System.Security.Cryptography.RandomNumberGenerator]::GetBytes(48))
try {
    az containerapp secret set --resource-group $ResourceGroup --name $AppName --secrets "crs-web-password=$password" "crs-web-session-key=$sessionSecret" -o none
    if ($LASTEXITCODE -ne 0) { throw 'Unable to create Azure web secrets.' }
}
finally { Remove-Variable password,passwordSecure,sessionSecret -ErrorAction SilentlyContinue }

Write-Host 'Updating app image and authentication secret references...'
az containerapp update --resource-group $ResourceGroup --name $AppName --image $image --set-env-vars "CRS_WEB_PASSWORD=secretref:crs-web-password" "CRS_WEB_SESSION_KEY=secretref:crs-web-session-key" "CRS_REQUIRE_DURABLE_DB=1" -o none
if ($LASTEXITCODE -ne 0) { throw 'Azure rejected the deployment. Check revision logs.' }
$ready = $false
for ($i=0; $i -lt 12; $i++) {
    $after = az containerapp show --resource-group $ResourceGroup --name $AppName -o json | ConvertFrom-Json
    if ($LASTEXITCODE -ne 0) { throw 'Could not inspect deployment.' }
    if ($after.properties.template.containers[0].image -eq $image -and $after.properties.runningStatus -eq 'Running' -and $after.properties.latestReadyRevisionName -eq $after.properties.latestRevisionName) {
        $ready = $true
        break
    }
    Start-Sleep -Seconds 5
}
if (-not $ready) { throw 'New revision did not become ready. Inspect revisions before proceeding.' }
$health = Invoke-RestMethod "$base/api/health" -TimeoutSec 60
if ($health.status -ne 'ok') { throw 'New revision returned unhealthy API status.' }
$source = Invoke-RestMethod "$base/api/crs/assistant/status" -Headers $headers -TimeoutSec 60
if (-not $source.corpus.ready -or $source.corpus.chunks -lt 40) { throw 'Official OSHA document corpus unavailable.' }
$stored = Invoke-RestMethod "$base/api/crs/scenarios/$sid" -Headers $headers -TimeoutSec 60
if ($stored.version -ne 1 -or $stored.conditions.depth_ft -ne 6) { throw 'Cross-revision persistence test failed.' }
Remove-Variable key,headers -ErrorAction SilentlyContinue
Write-Host ''
Write-Host 'CRS-RAG DEPLOYMENT VERIFIED'
Write-Host "Web platform: $base"
Write-Host "New image: $image"
Write-Host "New revision: $($after.properties.latestReadyRevisionName)"
Write-Host "OSHA sources: $($source.corpus.source_pages)"
Write-Host "Indexed passages: $($source.corpus.chunks)"
Write-Host "Azure OpenAI configured: $($source.model_configured)"
Write-Host 'Database persistence across revisions: PASS'
Write-Host "Prior image for rollback: $priorImage"
Write-Host "Prior ready revision: $priorRevision"
