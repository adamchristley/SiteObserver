# Azure research results: SiteObserver milestone 1

> Fill in **only measured and verified values**. Nothing below is a claimed deployment result until you execute the experiment.

**Experiment date:** TBD  
**Subscription type:** TBD (avoid recording subscription ID)  
**Region:** TBD  
**App host (optional public URL):** TBD  
**Commit SHA / GHCR image tag:** TBD  
**Resource configuration:** Container Apps consumption, 0.5 vCPU, 1 GiB, 0–1 replicas (planned)

## Objective

Evaluate first-time cloud deployment of the existing FastAPI construction-site simulator using Microsoft Azure Container Apps. Compare observed request latency and inspect resource/usage metrics, deployment success, and costs.

## Deployment evidence

| Observation | Result / screenshot |
| --- | --- |
| GitHub package build and publication | TBD |
| Container App provisioning state | TBD |
| Public `/health` HTTP response | TBD |
| Public `/api/site` sample response | TBD |
| CI status | TBD |

## Performance data

| Measurement | Actual result |
| --- | --- |
| Local API warm request latency, median of 10 | TBD |
| Azure API warm request latency, median of 10 | TBD |
| Azure API minimum / maximum over 10 | TBD |
| First request after idle (cold-start candidate) | TBD |
| Request successes / failures | TBD |

Describe laptop network, time of test, basic methodology and sampling limits. Do not equate end-to-end HTTP latency with model inference. In this milestone the model is a simulator, **not** a predictive ML model.

## Azure platform evidence

| Metric | Observed |
| --- | --- |
| Container Apps request count | TBD |
| CPU usage | TBD |
| Memory working set | TBD |
| Replicas (0 or 1) | TBD |
| Cost Management spending / available credit | TBD |
| Time period of the cost data | TBD |

## Engineering challenges

- Image registry selection and publication:
- Azure account, quotas, and deployment:
- Monitoring, scaling, and first-request behavior:
- Security: experiment is synthetic, public API excludes video endpoints, no credentials in repo.

## Conclusion / what comes next

**Completed:** TBD  
**Not completed:** Azure Static Web Apps frontend; construction-specific ML; validated incident prediction.

**Screenshots to capture:** GitHub Actions publish, Azure resource overview, successful health response, Azure Monitor metrics, Cost Management.

**Cleanup:** Confirm if test resource group was deleted and when.
