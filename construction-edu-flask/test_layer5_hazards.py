"""Layer 5 research scenarios: explicit water and utility conditions and selective changes.

These are checks of reported facts against a narrow rule subset. Not field
safety assessments or proof of OSHA compliance.
"""
import pytest
from crs.extractor import extract_conditions
from crs.state_resolver import create_from_text, revise_from_text
from crs_engine import CRSEngine, CRSInputError


def by_id(view):
    return {d['decision_id']: d for d in view['decisions']}


TEXT = (
    'Workers are inside a 6-foot trench without a protective system. '
    'Underground utilities are nearby, and standing water is accumulating '
    'in the excavation.'
)


def test_current_user_example_extracts_hazards_and_retains_unknowns():
    got = extract_conditions(TEXT)['conditions']
    assert got['depth_ft'] == 6
    assert got['employees_exposed'] is True
    assert got['water_accumulating'] is True
    assert got['utilities_expected'] is True
    assert 'water_precautions_adequate' not in got
    assert 'utility_locations_estimated' not in got
    assert 'excavation_opened' not in got


def test_original_example_gets_two_new_undetermined_decisions(tmp_path):
    e = CRSEngine(tmp_path / 'new_rules.sqlite3')
    result = create_from_text(e, TEXT)
    view = result['scenario']
    checks = by_id(view)
    assert len(checks) == 7  # Six narrow rule assessments plus one summary.
    assert checks['water_accumulation']['status'] == 'undetermined'
    assert checks['underground_utilities']['status'] == 'undetermined'
    assert checks['assessed_rules_summary']['status'] == 'undetermined'
    assert view['conditions']['water_accumulating'] is True
    assert view['conditions']['utilities_expected'] is True
    assert checks['water_accumulation']['regulations'][0]['id'] == '29 CFR 1926.651(h)(1)'
    assert checks['underground_utilities']['regulations'][0]['id'] == '29 CFR 1926.651(b)(1)'
    assert 'water_accumulating' in checks['water_accumulation']['depends_on']
    assert 'utility_locations_estimated' in checks['underground_utilities']['depends_on']


def test_water_correction_only_reassesses_water_and_aggregate(tmp_path):
    e = CRSEngine(tmp_path / 'water.sqlite3')
    start = create_from_text(e, TEXT)['scenario']
    sid = start['scenario_id']
    v2 = revise_from_text(e, sid, 'No adequate water precautions are in place.', 1)['scenario']
    assert v2['conditions']['water_precautions_adequate'] is False
    assert v2['reassessed_decisions'] == ['assessed_rules_summary', 'water_accumulation']
    assert by_id(v2)['water_accumulation']['status'] == 'noncompliant'
    assert by_id(v2)['underground_utilities']['evaluation_count'] == 1
    v3 = revise_from_text(e, sid, 'Adequate water precautions are in place.', 2)['scenario']
    assert v3['version'] == 3
    assert v3['reassessed_decisions'] == ['assessed_rules_summary', 'water_accumulation']
    assert by_id(v3)['water_accumulation']['status'] == 'compliant'
    assert by_id(v3)['underground_utilities']['evaluation_count'] == 1
    assert CRSEngine(tmp_path / 'water.sqlite3').get(sid)['version'] == 3
    assert len(e.history(sid)['state_events']) == 3
    assert by_id(v3)['water_accumulation']['evaluation_count'] == 3


def test_utility_rule_only_fails_when_open_and_locations_not_determined(tmp_path):
    e = CRSEngine(tmp_path / 'utilities.sqlite3')
    start = create_from_text(e, TEXT)['scenario']
    sid = start['scenario_id']
    v2 = revise_from_text(e, sid, 'Utility locations have not been determined.', 1)['scenario']
    assert v2['conditions']['utility_locations_estimated'] is False
    assert by_id(v2)['underground_utilities']['status'] == 'undetermined'
    v3 = revise_from_text(e, sid, 'The trench is already open.', 2)['scenario']
    assert v3['conditions']['excavation_opened'] is True
    assert by_id(v3)['underground_utilities']['status'] == 'noncompliant'
    assert v3['reassessed_decisions'] == ['assessed_rules_summary', 'underground_utilities']
    assert by_id(v3)['water_accumulation']['evaluation_count'] == 1
    v4 = revise_from_text(e, sid, 'Utility locations have been determined.', 3)['scenario']
    assert by_id(v4)['underground_utilities']['status'] == 'compliant'
    assert v4['reassessed_decisions'] == ['assessed_rules_summary', 'underground_utilities']


def test_water_no_employee_exposure_and_no_water(tmp_path):
    e = CRSEngine(tmp_path / 'notapplicable.sqlite3')
    a = e.create({'employees_exposed': False, 'water_accumulating': True,
                  'utilities_expected': True, 'utility_locations_estimated': False,
                  'excavation_opened': True})
    checks = by_id(a)
    assert checks['water_accumulation']['status'] == 'not_applicable'
    # Underground-location duty is independent of current employee exposure.
    assert checks['underground_utilities']['status'] == 'noncompliant'
    b = e.create({'employees_exposed': True, 'water_accumulating': False})
    assert by_id(b)['water_accumulation']['status'] == 'not_applicable'


def test_unknown_conditions_do_not_trigger_favorable_conclusions(tmp_path):
    e = CRSEngine(tmp_path / 'unknown.sqlite3')
    a = e.create({'employees_exposed': True, 'water_accumulating': True})
    assert by_id(a)['water_accumulation']['status'] == 'undetermined'
    assert by_id(a)['underground_utilities']['status'] == 'undetermined'
    b = e.create({'utilities_expected': True, 'utility_locations_estimated': False})
    assert by_id(b)['underground_utilities']['status'] == 'undetermined'


def test_invalid_boolean_types_rejected(tmp_path):
    e = CRSEngine(tmp_path / 'invalid.sqlite3')
    with pytest.raises(CRSInputError):
        e.create({'water_accumulating': 'yes'})
    with pytest.raises(CRSInputError):
        e.create({'utility_locations_estimated': 1})


def test_api_natural_language_retains_hazards_in_saved_state(tmp_path, monkeypatch):
    from app import app
    monkeypatch.delenv('CRS_DATABASE_URL', raising=False)
    monkeypatch.delenv('CRS_REQUIRE_DURABLE_DB', raising=False)
    monkeypatch.setenv('CRS_DB_PATH', str(tmp_path / 'http.sqlite3'))
    monkeypatch.setenv('CRS_API_KEY', 'test-layer-5-key')
    client = app.test_client()
    headers = {'Authorization': 'Bearer test-layer-5-key'}
    response = client.post('/api/crs/nl/scenarios', json={'text': TEXT}, headers=headers)
    assert response.status_code == 201
    created = response.json
    assert created['extraction']['conditions']['water_accumulating'] is True
    assert created['extraction']['conditions']['utilities_expected'] is True
    sid = created['scenario']['scenario_id']
    assert client.get(f'/api/crs/scenarios/{sid}', headers=headers).json['conditions']['water_accumulating'] is True
    lookup = client.get(f'/api/crs/scenarios/{sid}/osha', headers=headers)
    assert lookup.status_code == 200
    refs = {e['decision_id']: e for e in lookup.json['assessed_regulations']}
    assert refs['water_accumulation']['regulations'][0]['id'] == '29 CFR 1926.651(h)(1)'
    assert refs['underground_utilities']['regulations'][0]['id'] == '29 CFR 1926.651(b)(1)'
