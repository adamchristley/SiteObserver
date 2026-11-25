# Safe update of the existing CRS-RAG Azure Container App to a reviewed image.
# Usage: ./azure/upgrade-crs-rag.ps1 -ImageTag <40-character-merged-main-commit>
# Reads credentials only inside Cloud Shell; never prints them.
param(
  [Parameter(Mandatory=$true)]
  [ValidatePattern('^[a-f0-9]{40}$')]
  [string]$ImageTag,
  [string]$ResourceGroup = 'rg-siteobserver-reu',
  [string]$AppName = 'construction-edu-demo'
)
$ErrorActionPreference = 'Stop'
$image = "ghcr.io/adamchristley/construction-edu-demo:$ImageTag"
$key = $null
$hasUpdated = $false
try {
  $before = az containerapp show --resource-group $ResourceGroup --name $AppName -o json | ConvertFrom-Json
  if ($LASTEXITCODE -ne 0 -or -not $before) { throw 'Cannot inspect the currently deployed app.' }
  $previousImage = $before.properties.template.containers[0].image
  $fqdn = $before.properties.configuration.ingress.fqdn
  $base = "https://$fqdn"
  $key = az containerapp secret show --resource-group $ResourceGroup --name $AppName --secret-name crs-api-key --query value -o tsv
  if ($LASTEXITCODE -ne 0 -or -not $key) { throw 'Cannot retrieve the protected research API key.' }
  $headers = @{Authorization="Bearer $key"}
  $beforeStatus = Invoke-RestMethod "$base/api/crs/assistant/status" -Headers $headers -TimeoutSec 30
  if (-not $beforeStatus.corpus.ready) { throw 'Current corpus not ready. Stop and investigate.' }
  Write-Host "Previous image: $previousImage"
  Write-Host "New image: $image"
  Write-Host 'Updating container without changing its PostgreSQL or model secrets...'
  az containerapp update --resource-group $ResourceGroup --name $AppName --image $image -o none
  if ($LASTEXITCODE -ne 0) { throw 'Azure image update command failed.' }
  $hasUpdated = $true
  $ready = $false
  for($i=0;$i -lt 15;$i++){
    $after = az containerapp show --resource-group $ResourceGroup --name $AppName -o json | ConvertFrom-Json
    if ($LASTEXITCODE -eq 0 -and
        $after.properties.template.containers[0].image -eq $image -and
        $after.properties.runningStatus -eq 'Running' -and
        $after.properties.latestReadyRevisionName -eq $after.properties.latestRevisionName) {
      $ready=$true;break
    }
    Start-Sleep -Seconds 5
  }
  if (-not $ready) { throw 'Updated image did not become ready.' }
  $health = Invoke-RestMethod "$base/api/health" -TimeoutSec 30
  $status = Invoke-RestMethod "$base/api/crs/assistant/status" -Headers $headers -TimeoutSec 30
  if ($health.status -ne 'ok' -or -not $status.model_configured -or
      -not $status.corpus.ready -or $status.corpus.edition -ne '2025-07-01') {
    throw 'Health/model/index check failed. Historical PDF evidence not available or model disconnected.'
  }
  if ($status.corpus.scope -ne 'full_part_1926' -or
      $status.corpus.section_count -lt 260 -or
      @($status.corpus.subparts).Count -lt 28 -or
      $status.corpus.appendix_count -lt 25 -or
      $status.corpus.chunks -lt 500) {
    throw 'The new image does not contain the required COMPLETE Part 1926 text. Refusing deployment.'
  }
  foreach ($check in @(
      @{query='1926.451 scaffold';subpart='L';section='1926.451'},
      @{query='1926.501 fall protection';subpart='M';section='1926.501'},
      @{query='1926.651 excavation';subpart='P';section='1926.651'},
      @{query='1926.1053 ladder';subpart='X';section='1926.1053'},
      @{query='1926.1203 confined spaces';subpart='AA';section='1926.1203'}
    )) {
    $url = "$base/api/crs/assistant/search?q=$([uri]::EscapeDataString($check.query))&subpart=$($check.subpart)"
    $match = Invoke-RestMethod -Uri $url -Headers $headers -TimeoutSec 30
    if (-not @($match.chunks | Where-Object { $_.citation.StartsWith($check.section) }).Count) {
      throw "Part 1926 search smoke check failed for section $($check.section)."
    }
  }
  Write-Host 'Running two synthetic LLM scenario tests. Model token charges may apply.'
  $firstPayload = @{text='Workers are inside a six-foot trench without a protective system. Soil is not stable rock.'} | ConvertTo-Json
  $first = Invoke-RestMethod "$base/api/crs/assistant" -Method Post -Headers $headers -ContentType 'application/json' -Body $firstPayload -TimeoutSec 90
  if ($first.mode -ne 'azure_openai' -or -not $first.scenario.scenario_id -or
      @($first.retrieved_osha).Count -lt 1 -or
      @($first.citations).Count -lt 1) {
    throw 'Initial model or evidence attribution smoke test failed.'
  }
  $sid = $first.scenario.scenario_id
  $patchPayload = @{text='Correction: the trench is now 4 feet deep.';scenario_id=$sid;expected_version=$first.scenario.version} | ConvertTo-Json
  $changed = Invoke-RestMethod "$base/api/crs/assistant" -Method Post -Headers $headers -ContentType 'application/json' -Body $patchPayload -TimeoutSec 90
  $stored = Invoke-RestMethod "$base/api/crs/scenarios/$sid" -Headers $headers -TimeoutSec 30
  if ($changed.mode -ne 'azure_openai' -or $stored.version -ne 2 -or
      $stored.conditions.depth_ft -ne 4 -or @($changed.scenario.reassessed_decisions).Count -lt 1) {
    throw 'Reassessment/persistence smoke test failed.'
  }
  Write-Host ''
  Write-Host 'LIVE UPGRADE VERIFIED'
  Write-Host "SiteObserver: $base"
  Write-Host "Revision: $($after.properties.latestReadyRevisionName)"
  Write-Host "Part 1926 sections: $($status.corpus.section_count)"
  Write-Host "Subparts indexed: $(@($status.corpus.subparts).Count)"
  Write-Host "Regulatory passages: $($status.corpus.chunks)"
  Write-Host "Annual edition: $($status.corpus.edition)"
  Write-Host "Citation attribution on test: $($first.citation_attribution)"
  Write-Host 'GPT-4.1 mini inference: PASS'
  Write-Host 'Scenario version 1 to 2: PASS'
  Write-Host 'PostgreSQL stored depth: 4 feet'
  Write-Host "Reassessed decisions: $($changed.scenario.reassessed_decisions -join ', ')"
}
catch {
  Write-Warning "Upgrade did not pass validation: $($_.Exception.Message)"
  if ($hasUpdated -and $previousImage) {
    Write-Warning "Attempting rollback to previously recorded image $previousImage ..."
    az containerapp update --resource-group $ResourceGroup --name $AppName --image $previousImage -o none
    if ($LASTEXITCODE -ne 0) {
      Write-Warning 'Rollback command failed. Inspect Azure Container App revisions immediately.'
    }
  }
  throw
}
finally { Remove-Variable key,headers -ErrorAction SilentlyContinue }
