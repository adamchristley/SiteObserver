# Construction Education Flask Prompt Demo

This **public-safe demonstration** uses the already-written SiteObserver Prompt Lab web interface plus a Flask API, following the advisor's browser → Python backend → Azure service architecture. It does not publish the advisor's source, course documents, `.env` files, Azure credentials, chat history, or student records.

- `GET /`: serve prompt website
- `GET /api/health`: verify service connection
- `POST /api/prompt`: accept `{"prompt":"What is BIM?"}`, validate, and return a fixed demo acknowledgment
- `POST /chat`, `POST /cee_chat`, and `POST /api/chat`: compatibility aliases

**No AI model is connected**. The application only demonstrates hosting and genuine HTTP round trips.

## GitHub image build

The workflow **Publish construction education demo image** verifies Flask endpoints and publishes `ghcr.io/adamchristley/construction-edu-demo:latest` plus a commit-SHA tag. Check GitHub Actions for a successful run. Under Profile → Packages → construction-edu-demo → Package settings, make the **new sanitized image** public. Do not publish the supplied ZIP or its nested credentials.

## Deploy to your existing Azure Container Apps environment (PowerShell)

The Azure for Students subscription blocked Static Web Apps via region policy. Reuse the existing environment in `northcentralus` that successfully hosted SiteObserver:

```powershell
az account show --query "{name:name,state:state}" -o table
az containerapp create `
  --name construction-edu-demo `
  --resource-group rg-siteobserver-reu `
  --environment env-siteobserver-reu `
  --image ghcr.io/adamchristley/construction-edu-demo:latest `
  --ingress external `
  --target-port 8000 `
  --cpu 0.5 `
  --memory 1.0Gi `
  --min-replicas 0 `
  --max-replicas 1
```

If Azure reports registry authentication errors, confirm package visibility and follow Microsoft's Container Apps GHCR registry instructions.

```powershell
$fqdn = az containerapp show --name construction-edu-demo --resource-group rg-siteobserver-reu --query "properties.configuration.ingress.fqdn" -o tsv
$base = "https://$fqdn"
Start-Process $base
Invoke-RestMethod "$base/api/health"
Invoke-RestMethod -Method POST -Uri "$base/api/prompt" -ContentType 'application/json' -Body '{"prompt":"What is BIM?"}'
```

The existing `siteobserver-api` container is unchanged. Consumption has a monthly free grant, but usage can consume Azure student credits. Never wire up the supplied Azure OpenAI credentials without supervisor approval and a security review.
