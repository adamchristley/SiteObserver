"""Integration test for the durable PostgreSQL backend (CI supplies PostgreSQL)."""
import os
import pytest
from crs_engine import CRSEngine


@pytest.mark.skipif(not os.environ.get('CRS_TEST_POSTGRES_URL'),
                    reason='PostgreSQL service not configured')
def test_postgres_persistence_and_selective_reassessment(monkeypatch):
    monkeypatch.setenv('CRS_DATABASE_URL', os.environ['CRS_TEST_POSTGRES_URL'])
    engine = CRSEngine()
    first = engine.create({
        'employees_exposed': True, 'depth_ft': 6, 'stable_rock': False,
        'protective_system': 'none', 'competent_person_no_cave_in': False,
        'is_trench': True, 'safe_egress_within_25ft': True,
        'spoil_hazard': True, 'spoil_distance_ft': 3, 'spoil_retained': False,
        'inspection_before_work': True, 'rain_event': False,
    })
    sid = first['scenario_id']
    changed = CRSEngine().revise(sid, {'depth_ft': 4}, expected_version=1)
    assert changed['reassessed_decisions'] == [
        'assessed_rules_summary', 'protective_system', 'trench_egress']
    assert set(changed['unchanged_decisions']) == {'inspection', 'spoils', 'water_accumulation', 'underground_utilities'}
    ds = {d['decision_id']: d for d in changed['decisions']}
    assert ds['inspection']['evaluation_count'] == 1
    assert ds['trench_egress']['evaluation_count'] == 2
    reloaded = CRSEngine().get(sid)
    assert reloaded['version'] == 2
    assert reloaded['conditions']['depth_ft'] == 4
    assert len(CRSEngine().history(sid)['decision_events']) == 10
    alternative = CRSEngine().branch(sid, 'what_if')
    assert alternative['parent_branch'] == 'base'
    assert CRSEngine().get(sid)['conditions']['depth_ft'] == 4
