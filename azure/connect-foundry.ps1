# Connect an existing Foundry chat deployment to SiteObserver.
# Run in Azure Cloud Shell PowerShell. A small model call may be billed.
param(
  [string]$ResourceGroup = 'rg-siteobserver-reu',
  [string]$AppName = 'construction-edu-demo',
  [string]$DeploymentName = 'gpt-4.1-mini'
)
$ErrorActionPreference = 'Stop'
$foundryKey = $null
$crsKey = $null
try {
  $accountsJson = az cognitiveservices account list --resource-group $ResourceGroup --output json
  if ($LASTEXITCODE -ne 0) { throw 'Could not list Foundry resources.' }
  $accounts = @($accountsJson | ConvertFrom-Json)
  $matches = @()
  foreach ($account in $accounts) {
    if ($account.kind -notin @('AIServices','OpenAI')) { continue }
    $deployed = az cognitiveservices account deployment show --resource-group $ResourceGroup --name $account.name --deployment-name $DeploymentName --query name -o tsv 2>$null
    if ($LASTEXITCODE -eq 0 -and $deployed -eq $DeploymentName) { $matches += $account }
  }
  if ($matches.Count -ne 1) {
    $accounts | Select-Object name,kind,location | Format-Table | Out-Host
    throw "Found $($matches.Count) AI resources with deployment $DeploymentName, expected exactly one."
  }
  $foundry = $matches[0]
  $endpoint = [string]$foundry.properties.endpoint
  if (-not $endpoint) { $endpoint = az cognitiveservices account show --resource-group $ResourceGroup --name $foundry.name --query 'properties.endpoint' -o tsv }
  if (-not $endpoint) { throw 'Foundry endpoint unavailable.' }
  $uri = [Uri]$endpoint
  if ($uri.Scheme -ne 'https' -or -not ($uri.Host.EndsWith('.openai.azure.com') -or $uri.Host.EndsWith('.services.ai.azure.com'))) { throw 'Unexpected Foundry endpoint. Review your Get code page.' }
  $endpoint = $endpoint.TrimEnd('/')
  Write-Host "Foundry resource: $($foundry.name)"
  Write-Host "Foundry endpoint: $endpoint"
  Write-Host "Model deployment: $DeploymentName"
  $foundryKey = az cognitiveservices account keys list --resource-group $ResourceGroup --name $foundry.name --query key1 -o tsv
  if ($LASTEXITCODE -ne 0 -or -not $foundryKey) { throw 'Unable to access Foundry API key; check permissions.' }
  Write-Host 'Testing chat JSON endpoint with one small, potentially billed request...'
  $ping = @{
    model = $DeploymentName
    messages = @(
      @{role='system';content='Respond with JSON only.'}
      @{role='user';content='Reply with a JSON object containing status equal to ok.'}
    )
    response_format = @{type='json_object'}
    max_tokens = 80
  } | ConvertTo-Json -Depth 6
  try {
    $reply = Invoke-RestMethod -Uri "$endpoint/openai/v1/chat/completions" -Method Post -Headers @{'api-key'=$foundryKey} -ContentType 'application/json' -Body $ping -TimeoutSec 60
  } catch {
    throw "Foundry model test failed before changing SiteObserver: $($_.Exception.Message)"
  }
  if (-not $reply.choices[0].message.content) { throw 'Foundry did not return a supported chat response.' }
  Write-Host 'Direct Foundry model test passed.'
  az containerapp secret set --resource-group $ResourceGroup --name $AppName --secrets "crs-azure-openai-key=$foundryKey" -o none
  if ($LASTEXITCODE -ne 0) { throw 'Failed to save API key to Container App secrets.' }
  az containerapp update --resource-group $ResourceGroup --name $AppName --set-env-vars "AZURE_OPENAI_ENDPOINT=$endpoint" "AZURE_OPENAI_DEPLOYMENT=$DeploymentName" 'AZURE_OPENAI_API_KEY=secretref:crs-azure-openai-key' -o none
  if ($LASTEXITCODE -ne 0) { throw 'Container App configuration update failed.' }
  $crsKey = az containerapp secret show --resource-group $ResourceGroup --name $AppName --secret-name crs-api-key --query value -o tsv
  if ($LASTEXITCODE -ne 0 -or -not $crsKey) { throw 'Unable to read research API key for verification.' }
  $fqdn = az containerapp show --resource-group $ResourceGroup --name $AppName --query 'properties.configuration.ingress.fqdn' -o tsv
  $base = "https://$fqdn"
  $ready = $false
  for ($i=0; $i -lt 12; $i++) {
    try {
      $status = Invoke-RestMethod -Uri "$base/api/crs/assistant/status" -Headers @{Authorization="Bearer $crsKey"} -TimeoutSec 25
      if ($status.model_configured -eq $true -and $status.corpus.ready -eq $true) { $ready=$true;break }
    } catch {}
    Start-Sleep -Seconds 5
  }
  if (-not $ready) { throw 'New revision did not report Foundry configuration. Inspect the Container App revisions and logs.' }
  Write-Host 'FOUNDRY CONNECTION CONFIGURED'
  Write-Host "SiteObserver: $base"
  Write-Host "Model: $DeploymentName"
  Write-Host "OSHA indexed passages: $($status.corpus.chunks)"
  Write-Host 'Model configured: True'
  Write-Host 'Next: test a synthetic scenario through the website for end-to-end validation.'
} finally {
  Remove-Variable foundryKey,crsKey -ErrorAction SilentlyContinue
}
