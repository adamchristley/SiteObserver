import os
import pytest
from crs_engine import CRSEngine, CRSInputError, CRSVersionConflict
from app import app


@pytest.fixture
def engine(tmp_path):
    return CRSEngine(tmp_path / 'test.sqlite3')


def initial():
    return {
        'employees_exposed': True, 'depth_ft': 6, 'stable_rock': False,
        'protective_system': 'none', 'competent_person_no_cave_in': False,
        'is_trench': True, 'safe_egress_within_25ft': True,
        'spoil_hazard': True, 'spoil_distance_ft': 3, 'spoil_retained': False,
        'inspection_before_work': True, 'rain_event': False,
    }


def dmap(view):
    return {d['decision_id']: d for d in view['decisions']}


def test_create_grounded_trace_and_versions(engine):
    view = engine.create(initial())
    assert view['version'] == 1
    assert dmap(view)['protective_system']['status'] == 'noncompliant'
    assert dmap(view)['trench_egress']['status'] == 'compliant'
    assert dmap(view)['spoils']['status'] == 'compliant'
    assert dmap(view)['inspection']['status'] == 'compliant'
    assert dmap(view)['assessed_rules_summary']['status'] == 'noncompliant'
    protective = dmap(view)['protective_system']
    assert protective['regulations'][0]['id'] == '29 CFR 1926.652(a)(1)'
    assert all('state_id' in e for e in protective['evidence_states'])
    assert engine.get(view['scenario_id'])['conditions'] == initial() | {'depth_ft': 6.0, 'spoil_distance_ft': 3.0}


def test_selective_reassessment_and_reverse_dependency(engine):
    first = engine.create(initial())
    sid = first['scenario_id']
    changed = engine.revise(sid, {'depth_ft': 4}, expected_version=1)
    assert changed['reassessed_decisions'] == ['assessed_rules_summary', 'protective_system', 'trench_egress']
    assert set(changed['unchanged_decisions']) == {'inspection', 'spoils'}
    assert dmap(changed)['trench_egress']['evaluation_count'] == 2
    assert dmap(changed)['inspection']['evaluation_count'] == 1
    assert dmap(changed)['spoils']['evaluated_version'] == 1
    # A 4-ft excavation without the required competent-person exception stays noncompliant.
    assert dmap(changed)['protective_system']['status'] == 'noncompliant'
    fixed = engine.revise(sid, {'competent_person_no_cave_in': True}, expected_version=2)
    assert fixed['reassessed_decisions'] == ['assessed_rules_summary', 'protective_system']
    assert dmap(fixed)['protective_system']['status'] == 'compliant'
    assert dmap(fixed)['trench_egress']['evaluation_count'] == 2
    assert dmap(fixed)['assessed_rules_summary']['evaluation_count'] == 3
    assert len(engine.history(sid)['decision_events']) == 10  # 5 initial + 3 + 2


def test_noop_and_remove_facts(engine):
    first = engine.create(initial())
    sid = first['scenario_id']
    no_change = engine.revise(sid, {'depth_ft': 6})
    assert no_change['version'] == 1
    assert no_change['reassessed_decisions'] == []
    missing = engine.revise(sid, {'depth_ft': None})
    assert missing['version'] == 2
    assert dmap(missing)['protective_system']['status'] == 'undetermined'
    assert dmap(missing)['trench_egress']['status'] == 'undetermined'
    assert not any(x['condition'] == 'depth_ft' for x in missing['active_states'])


def test_branch_revision_does_not_mutate_actual_state(engine):
    first = engine.create(initial())
    sid = first['scenario_id']
    alt = engine.branch(sid, 'what_if')
    assert alt['parent_branch'] == 'base'
    changed = engine.revise(sid, {'depth_ft': 4, 'competent_person_no_cave_in': True}, 'what_if')
    assert dmap(changed)['protective_system']['status'] == 'compliant'
    assert engine.get(sid, 'base')['conditions']['depth_ft'] == 6
    assert dmap(engine.get(sid, 'base'))['protective_system']['status'] == 'noncompliant'
    assert engine.history(sid, 'what_if')['state_events'][0]['operation'] == 'BRANCH'


def test_egress_boundary_spoil_retainment_rain(engine):
    base = engine.create(initial())
    sid = base['scenario_id']
    v = engine.revise(sid, {'depth_ft': 3.9, 'spoil_distance_ft': 1,
                            'safe_egress_within_25ft': False, 'rain_event': True,
                            'inspection_after_rain': False})
    ds = dmap(v)
    assert ds['trench_egress']['status'] == 'not_applicable'
    assert ds['spoils']['status'] == 'noncompliant'
    assert ds['inspection']['status'] == 'noncompliant'
    v = engine.revise(sid, {'spoil_retained': True, 'inspection_after_rain': True})
    assert dmap(v)['spoils']['status'] == 'compliant'
    assert dmap(v)['inspection']['status'] == 'compliant'


def test_validation_and_optimistic_concurrency(engine):
    with pytest.raises(CRSInputError):
        engine.create({'depth_ft': -1})
    with pytest.raises(CRSInputError):
        engine.create({'depth_ft': '6'})
    with pytest.raises(CRSInputError):
        engine.create({'secret': 'ignore'})
    first = engine.create(initial())
    with pytest.raises(CRSVersionConflict):
        engine.revise(first['scenario_id'], {'depth_ft': 4}, expected_version=3)
    assert engine.get(first['scenario_id'])['version'] == 1
    with pytest.raises(CRSInputError):
        engine.branch(first['scenario_id'], '../bad')


def test_flask_api_secured_and_end_to_end(tmp_path, monkeypatch):
    monkeypatch.setenv('CRS_DB_PATH', str(tmp_path / 'api.sqlite3'))
    monkeypatch.delenv('CRS_API_KEY', raising=False)
    client = app.test_client()
    assert client.post('/api/crs/scenarios', json={'conditions': initial()}).status_code == 403
    monkeypatch.setenv('CRS_API_KEY', 'local-test-key')
    hdr = {'Authorization': 'Bearer local-test-key'}
    assert client.get('/api/crs/regulations', headers=hdr).status_code == 200
    r = client.post('/api/crs/scenarios', json={'conditions': initial()}, headers=hdr)
    assert r.status_code == 201
    sid = r.json['scenario_id']
    r = client.patch(f'/api/crs/scenarios/{sid}/conditions',
                     json={'changes': {'depth_ft': 4}, 'expected_version': 1}, headers=hdr)
    assert r.status_code == 200
    assert r.json['reassessed_decisions'] == ['assessed_rules_summary', 'protective_system', 'trench_egress']
    assert client.get(f'/api/crs/scenarios/{sid}/history', headers=hdr).json['state_events'][-1]['operation'] == 'REVISE'
    assert client.post(f'/api/crs/scenarios/{sid}/branches',
                       json={'name': 'alternative'}, headers=hdr).status_code == 201
    assert client.get(f'/api/crs/scenarios/{sid}?branch=base', headers=hdr).status_code == 200
    assert client.get('/api/crs/scenarios/not-real', headers=hdr).status_code == 404
    assert client.patch(f'/api/crs/scenarios/{sid}/conditions',
                        json={'changes': {'depth_ft': 7}, 'expected_version': 1}, headers=hdr).status_code == 409
