# EX-01 evaluation and historical OSHA reference handoff

## What this revision fixes

The assistant now always includes actually retrieved OSHA passages in the response field retrieved_osha. Its citation_attribution field distinguishes model_supported, retrieval_only and none. A retrieval-only reference does NOT prove the model cited or correctly applied that source.

The supplied July 2025 Part 1926 Subpart P is separately indexed as a historical reference, with 85 extracted text passages, pages 337 to 373, the source PDF SHA-256 and explicit edition metadata. Newer build-time OSHA/GovInfo source text is retained as the primary corpus. The supplied 2025 PDF contains diagrams and engineering figures in its appendices that are not reliably searchable from the extracted text; these require review in the original PDF.

## Private 15-turn live evaluation

The adviser workbook EX-01_15_Dialogues_Ground_Truth.xlsx was intentionally not committed to this public GitHub repository.

1. Open Azure Cloud Shell at https://shell.azure.com/ and select PowerShell.
2. Use Manage files > Upload to upload the attached EX-01_15_Dialogues_Ground_Truth.xlsx to /home/achristl/.
3. After deploying the merged fixes, run:

    cd /home/achristl/SiteObserver
    git pull origin main
    $rg = "rg-siteobserver-reu"
    $app = "construction-edu-demo"
    $key = az containerapp secret show --name $app --resource-group $rg --secret-name crs-api-key --query value -o tsv
    $env:SITEOBSERVER_API_KEY = $key
    Remove-Variable key
    try {
      python azure/run_ex01_live.py /home/achristl/EX-01_15_Dialogues_Ground_Truth.xlsx --base https://construction-edu-demo.graydesert-cb959016.northcentralus.azurecontainerapps.io --output /home/achristl/ex01-live-results.json --confirm-model-billing
    } finally {
      Remove-Item Env:SITEOBSERVER_API_KEY -ErrorAction SilentlyContinue
    }

This makes up to 15 potentially billed GPT-4.1 mini requests and creates synthetic scenarios in the persistent research database. It does not commit the test workbook or expose secret values.

The JSON report includes each expected versus actual status, section-level OSHA recall, model-supported citations, conflict flags, version increments, selective reassessment and dependency proposal counts. It does not contain the raw dialogue inputs.

## Interpreting the adviser benchmarks

The workbook contains 15 turns in three distinct dialogues (shield and worker exposure, depth and soil protection, egress and conflicting reports). The expected outcome for EX-01-B2 is Approved. The research system intentionally cannot issue field-work approval, so exact match on the full workbook cannot reach 100% without an advisor decision about how to label hypothetical approvals. Do not silently change the workbook or treat a safe-sounding model output as permission to begin construction.

Model citations from the retrieved passages are distinct from retrieval-only references. Section-level recall is a research metric; it does not establish paragraph-level legal applicability. Human expert review remains necessary.

## Deploy this revision

After the fix PR is merged, wait for the main-branch GHCR publish workflow to succeed. Then in Cloud Shell PowerShell:

    cd /home/achristl/SiteObserver
    git pull origin main
    ./azure/upgrade-crs-rag.ps1 -ImageTag <VERIFIED-FULL-MAIN-COMMIT-SHA>

The script preserves PostgreSQL and Foundry secrets, tests the indexed 2025 reference, and runs two synthetic model/database checks. It attempts rollback to the previous image if verification fails.

## Limitations

This is a research prototype, not an operational OSHA compliance service. The historical PDF excerpts are text-only, the current primary source is a snapshot, and model-generated dependency edges remain unapproved proposals. Before publication or field use, evaluate every dialogue with expert review, accuracy and citation precision; address appendix diagrams, regulatory change monitoring, identity/access controls and multiuser isolation.
