# SiteObserver: All of 29 CFR Part 1926

## July 2025 evaluation corpus

The current Docker build indexes the complete 2025 annual Part 1926 granule from GovInfo. It checks the edition, full source SHA-256 and structural inventory. The earlier rolling eCFR build documented below is retained here for historical comparison. See [the evaluation handoff](EX01_EVALUATION_HANDOFF.md).

## Earlier rolling eCFR implementation

SiteObserver now ingests the entire official 29 CFR Part 1926 text snapshot at Docker build time. This expands the OSHA corpus beyond Excavations (Subpart P) to other construction safety regulations, appendices and associated headings. It does **not** turn the six existing excavation checks into a complete OSHA compliance engine. The broader model only proposes research findings for human review.

Official source (primary): https://www.govinfo.gov/bulkdata/ECFR/title-29/ECFR-title29.xml
OSHA Part 1926 overview: https://www.osha.gov/laws-regs/regulations/standardnumber/1926

The Government Publishing Office is the source of the current eCFR XML. The existing July 2025 PDF reference remains historically labeled, not the primary current-law source.

### Verified Docker-build snapshot

An actual GitHub Actions Docker build (not an estimate) extracted:

- 292 regulatory sections
- 29 subparts
- 40 appendices
- 11,632 searchable passages

The build records retrieval time and the government archive SHA-256. Exact counts may change with future revisions. To avoid claiming whole-part coverage from incomplete data, it rejects images with missing major sections or below the configured section/subpart/appendix counts.

Official regulation pages and the GovInfo source archive are linked from each passage. The parser extracts available text and table rows, and flags passages with source graphics for expert review. A graphic flag does not imply that an engineering table or figure is fully machine-readable.

## Architecture

1. At image build, crs.part1926_ingest downloads official GovInfo Title 29 XML, isolates Part 1926, preserves section and subpart structure, and rejects an incomplete corpus. Runtime does not download third-party regulatory URLs.
2. crs.document_rag.OSHAIndex indexes all passages once per application worker. Search is BM25 lexical retrieval with full-section citations, subpart filtering, source edition metadata and an optional exact-citation boost. Semantic vector embeddings are not included.
3. The authenticated GET /api/crs/assistant/search accepts q, limit (1-12) and an optional one- or two-letter subpart. The browser has an independent OSHA source explorer.
4. GPT-4.1 mini can extract the predefined excavation conditions plus namespaced obs_* observations for other construction hazards. Only explicit, small, validated typed values are stored. New observations cannot masquerade as certified rules.
5. The PostgreSQL scenario engine persists all supported conditions and observations, hypothetical branches and version histories. Six excavation checks plus the summary remain predefined deterministic assessments.
6. LLM-proposed decision types and their dependency edges are recorded separately as research candidates. Changes to their observed input facts mark affected candidate decisions for reassessment. Nothing automatically approves construction work.
7. Hypothetical branches inherit the candidate dependency context but reset it to needs_review, ensuring branch-specific changes do not silently reuse prior decisions.

## Supported research examples

- Subpart L: scaffolds, platforms, guarded access and fall protection related to scaffolds.
- Subpart M: fall protection, guardrails, safety nets and personal fall-arrest systems.
- Subpart K: electrical equipment and safe work practices.
- Subpart P: excavations, existing deterministic checks and 2025 historical reference.
- Subpart X: ladders and stairways.
- Subpart AA: confined spaces in construction.
- Subpart CC: cranes and derricks.
- The remaining Part 1926 subparts are indexed but require separate case-specific evaluation before claiming model reliability.

These are retrieval and provisional research-analysis capabilities, not validated compliance determinations.

## Tests and release

The repository's Publish construction education demo image workflow runs the legacy regression suite, generalized observation and branching tests, full corpus completeness tests, source exploration API tests and a Docker smoke build downloading the complete government XML.

When PR #10 has passed both jobs and is merged, GitHub Actions publishes an image to:

    ghcr.io/adamchristley/construction-edu-demo:<40-character-merged-main-SHA>

Use the authenticated Azure Cloud Shell and the guarded existing upgrader, which verifies:
- full_part_1926 scope
- sufficient section, subpart and appendix counts
- live search across Scaffold (L), Fall Protection (M), Excavations (P), Ladders (X), and Confined Spaces (AA)
- configured GPT-4.1 mini service
- two real synthetic scenario model calls, version changes and PostgreSQL persistence

    cd /home/achristl/SiteObserver
    git pull origin main
    ./azure/upgrade-crs-rag.ps1 -ImageTag <MERGED-MAIN-COMMIT-SHA>

No credentials should be committed or shared. Model requests may be billed. If post-deployment checks fail the upgrade script attempts to restore the previous image.

## Research evaluation and limitations

The EX-01 Excel workbook evaluates 15 excavation-focused turns only; it is not sufficient evidence for full Part 1926 reasoning. Retain it for regression and create separate expert-reviewed dialogues for each additional subpart.

Required research validation includes:
- Paragraph-specific precision and recall, not only section-level keyword overlap
- Fact extraction accuracy and provenance across construction domains
- False approvals, unsupported/model-invented claims and citation coverage
- Explicit expert review of inferred dependency edges and candidate decisions
- Cross-subpart interactions and conflicts between standards
- Appendix tables, charts and graphics, which text indexing may not fully represent
- Source refresh/change detection and reconsideration of decisions that depend on changed regulations
- Secure multi-user authorization and full auditability before any external deployment

The shared-password site is a trusted research preview, not a public safety compliance portal.
