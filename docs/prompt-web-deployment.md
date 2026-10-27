# SiteObserver Prompt Lab on Azure Static Web Apps

This is a separate, lightweight prompt web app. It does not replace the React construction safety dashboard or modify the Azure Container Apps deployment.

## Purpose
A user can open the site over HTTPS, enter a prompt, and send it via POST /api/prompt. The managed Azure Function returns an HTTP 200 JSON response with a unique request ID and fixed acknowledgment. GET /api/health is used for connectivity checking. **No AI model is connected.** No request content is persisted by the demo. Do not send sensitive prompts into a public, unauthenticated prototype.

## Create and deploy in Azure Portal
1. Visit https://portal.azure.com > Create a resource > Static Web App.
2. Subscription: Azure for Students. Plan: **Free**. Name: `siteobserver-prompt-web`. Resource group: `rg-siteobserver-reu` if allowed by its region policy. For the managed Functions region, select a region permitted by the subscription, if one is available.
3. Source: GitHub. Organization: `adamchristley`. Repository: `SiteObserver`. Branch: `main`.
4. Build preset: **Custom**. Enter:
   - **App location:** `prompt-web`
   - **API location:** `prompt-api`
   - **Output location:** leave blank (static HTML, no build output folder)
5. Create the resource. Azure will add a deployment workflow in `.github/workflows/` to publish the app and API. Wait for a successful run.
6. Use the actual website URL from the Azure resource Overview tab. Open it, confirm /api/health displays HTTP 200, then send a test prompt and verify the returned acknowledgment.

The API uses the Azure Static Web Apps managed Functions integration and is included on the Free plan within applicable limits. No keys, paid external API, App Service, or Container Apps linkage are required.

## Local tests
Run `cd prompt-api && npm install && npm test` to check the demo response. With Azure Static Web Apps CLI and Azure Functions Core Tools installed, run `swa start prompt-web --api-location prompt-api` from the repository root.

## Next milestone
After your advisor specifies an AI provider, implement an authenticated backend call in the managed Function. Store secrets only in Azure application settings, add rate limits, and confirm potential provider costs. Never embed API keys in browser JavaScript.
