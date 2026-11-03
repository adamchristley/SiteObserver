# CRS-RAG Layer 5: water and underground-utility decisions

This iteration extends the existing research-only, deterministic assessment system. The original four OSHA rule checks are retained and two more scoped assessment rules are added. **None of these constitute a comprehensive OSHA compliance determination or on-site safety advice.**

## Rules added

- **Water accumulation, 29 CFR 1926.651(h)(1)**: `water_accumulating`, `water_precautions_adequate`, and `employees_exposed`. Missing adequacy information results in `undetermined`. Explicit absence of adequate precautions with exposed employees and accumulating water results in `noncompliant`. An explicit claim of adequate precautions can produce a narrow `compliant` assessment **based only on user-reported information**, not verified on site. The rule also contains important examples of different precautions, and requires situation-specific judgment.
- **Estimated utility locations, 29 CFR 1926.651(b)(1)**: `utilities_expected`, `utility_locations_estimated`, and `excavation_opened`. An opened excavation where expected utilities were not previously located results in `noncompliant` for this specific paragraph. Missing facts result in `undetermined`. This does **not** implement OSHA 1926.651(b)(2) through (4) for utility owner contact, exact-location determination and protection.

Official source: https://www.osha.gov/laws-regs/regulations/standardnumber/1926/1926.651

## Parsing and state storage

The natural-language extractor now saves conditions when supported phrases are explicitly present:

- "Underground utilities are nearby" -> `utilities_expected=true`
- "Standing water is accumulating in the excavation" -> `water_accumulating=true`
- "No adequate water precautions are in place" -> `water_precautions_adequate=false`
- "Adequate water precautions are in place" -> `water_precautions_adequate=true` (an **unverified user claim**)
- "Utility locations have not been determined" -> `utility_locations_estimated=false`
- "The trench is already open" -> `excavation_opened=true`

The API endpoints remain unchanged and API-key protected:

- `POST /api/crs/nl/scenarios` creates a scenario from English.
- `POST /api/crs/nl/scenarios/<sid>/messages` applies factual corrections with `expected_version`.
- `GET /api/crs/scenarios/<sid>` displays the current state and decisions.
- `GET /api/crs/scenarios/<sid>/history` displays revision events.
- `GET /api/crs/scenarios/<sid>/osha` retrieves currently relevant OSHA citations and the assessed rules.

The dependency index automatically tracks these new conditions, so a change to `water_precautions_adequate` rechecks **water_accumulation** and **assessed_rules_summary**, but not **underground_utilities**, **inspection**, **spoils**, **trench_egress**, or **protective_system**.

## Compatibility and limitations

- New scenarios receive **six** specific rule assessments and one summary decision. Older persisted scenarios may still contain only the original four checks until a separately reviewed migration/reassessment procedure is implemented. Do not interpret an old scenario's original summary as covering the newly added rules.
- The OSHA research catalog is now `osha-subpart-p-excavation-v2`. Earlier catalog snapshots are flagged by version drift; this does not automatically re-evaluate earlier decisions.
- The extractor is intentionally incomplete. It does not validate whether safeguards are truly adequate, cannot reliably interpret arbitrary dialogue and does not automatically fetch up-to-date regulations.
- Do not expose `CRS_API_KEY` in browser JavaScript. This milestone does not change the public prompt demo interface.
- No additional cloud resources or paid language model APIs are required.

## Tests

```bash
python -m pip install Flask==3.1.1 pytest
python -m pytest -q construction-edu-flask/test_crs.py construction-edu-flask/test_nl_pipeline.py construction-edu-flask/test_osha_retrieval.py construction-edu-flask/test_layer5_hazards.py
```

The repository's publish workflow also runs those tests and the PostgreSQL integration test against a disposable CI database. To verify against Azure, use synthetic test scenarios and never paste the API secret into chat.
