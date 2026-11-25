# Conversational assessment and private functional evaluation

The conversational assessment uses the July 1, 2025 annual edition of 29 CFR Part 1926. The Docker build verifies the GovInfo granule digest and inventory before indexing it. The reported 304 section entries include reserved entries and ranges. The source also contains 40 appendices and 29 named subparts, including reserved BB. Figures and complex engineering tables still require inspection of the official source. This edition is a fixed research reference.

| Research status | Criterion |
| --- | --- |
| Approved | The defined task has affirmative evidence for all applicable scoped checks, including the competent person's verification of applicable hazards. |
| Not Approved | A reported condition or proposed operation fails an applicable requirement. |
| Pending Verification | A specific report, correction, conflict or proposed control requires verification. |
| Insufficient Information | An essential fact is missing and no stronger conclusion is supported. |

Approved applies only to the stipulated research task. Authorized site personnel retain work authorization. Requires Expert Review is a warning. The lower-level diagnostics retain their original schema for existing API clients.

Each scoped finding stores its current status, paragraph identifiers, version, reason and the state IDs of facts used. Missing prerequisites are recorded so that later evidence can trigger reassessment. Read the changed, reassessed, unchanged and retired sets separately. A decision can be reassessed and keep its status. An inherited approval applies only to its original area and conditions. The chat pane exposes current findings, actions and source passages. Developer Mode contains implementation diagnostics. Generate brief opens the print view for the current assessment.

## Run the private workbook locally

Using Python with Flask and Beautiful Soup installed, from the repository root:

```sh
(cd construction-edu-flask && python -m crs.annual_cfr)
python azure/run_ex01_live.py /path/to/original.xlsx --local --output /private/path/local-evaluation.json
```

The local run uses Flask endpoints, isolated SQLite state and deterministic extraction. The workbook is opened read-only. Only the input column is sent to the assistant. The report contains private scenario facts, evidence and reasoning. Keep it outside the repository.

## Run on the updated Azure deployment

After deploying the tested revision with the existing Azure upgrade script, run this from an authenticated environment with SITEOBSERVER_API_KEY set:

```sh
python azure/run_ex01_live.py /path/to/original.xlsx --base "$SITEOBSERVER_BASE" --output /private/path/live-evaluation.json --confirm-model-billing
```

The live run verifies the corpus edition and scope, checks inference mode on each turn, and creates synthetic research scenarios. Keep the original baseline. Compare status exact matches, paragraph precision and recall, changed conditions, missed and unnecessary reassessments, retained evidence and each decision's dependencies against the workbook narratives. Model-attributed citations, rule-supported citations and search hits have different meanings. The workbook has prose decision updates rather than exhaustive edge annotations. Document any reviewer interpretation separately.

Formal evaluation requires unseen dialogues and independent review of the decisions and the applicability of the cited paragraphs.
