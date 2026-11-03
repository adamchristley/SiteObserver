"""Regression cases for the first no-LLM natural-language CRS research milestone."""
import pytest

from crs.extractor import extract_conditions
from crs.state_resolver import create_from_text, revise_from_text
from crs_engine import CRSEngine, CRSInputError, CRSVersionConflict


@pytest.fixture
def engine(tmp_path):
    return CRSEngine(tmp_path / 'nl_test.sqlite3')


def decisions(view):
    return {d['decision_id']: d for d in view['decisions']}


def test_explicit_scenario_extraction():
    parsed = extract_conditions('Workers are inside a 6-foot trench without a protective system.')
    assert parsed['conditions'] == {
        'employees_exposed': True, 'depth_ft': 6.0,
        'is_trench': True, 'protective_system': 'none',
    }
    assert 'depth_ft' in parsed['evidence']
    assert 'stable_rock' not in parsed['conditions']


def test_correction_without_repeating_entire_scenario():
    parsed = extract_conditions('Actually, the trench is only 4 feet deep.')
    assert parsed['conditions']['depth_ft'] == 4
    assert parsed['conditions']['is_trench'] is True
    assert 'protective_system' not in parsed['conditions']


def test_inches_and_spoils_do_not_confuse_depth():
    parsed = extract_conditions('The trench is 72 inches deep, and spoil piles are 3 feet from the edge.')
    assert parsed['conditions']['depth_ft'] == 6
    assert parsed['conditions']['spoil_distance_ft'] == 3


def test_mere_site_workers_do_not_imply_exposure():
    assert 'employees_exposed' not in extract_conditions('Workers are on site near the trench.')['conditions']
    assert extract_conditions('No workers are inside the trench.')['conditions']['employees_exposed'] is False


def test_protection_presence_not_assumed_verified():
    got = extract_conditions('A trench box is installed in the excavation.')['conditions']
    assert got['protective_system'] == 'present_unverified'
    assert extract_conditions('The protective system is verified.')['conditions']['protective_system'] == 'verified'
    assert extract_conditions('Without shoring in the trench.')['conditions']['protective_system'] == 'none'


def test_unknown_information_stays_unknown():
    parsed = extract_conditions('There is a trench. The crew is discussing the project.')
    assert parsed['conditions'] == {'is_trench': True}


def test_conflicting_values_are_not_silently_overwritten():
    with pytest.raises(CRSInputError, match='Conflicting'):
        extract_conditions('The trench is 6 feet deep, but the excavation is 4 feet deep.')


def test_invalid_and_unrecognized_input(engine):
    for text in ('', ' ' * 6, None, 'A nice sunny day'):
        with pytest.raises(CRSInputError):
            create_from_text(engine, text)


def test_create_and_correct_selectively(engine):
    created = create_from_text(engine, 'Workers are inside a 6-foot trench without a protective system.')
    first = created['scenario']
    sid = first['scenario_id']
    assert first['version'] == 1
    assert decisions(first)['protective_system']['status'] == 'undetermined'  # stable rock unknown
    revised = revise_from_text(engine, sid, 'Actually, the trench is only 4 feet deep.', 1)
    state = revised['scenario']
    assert state['version'] == 2
    assert set(state['reassessed_decisions']) == {
        'protective_system', 'trench_egress', 'assessed_rules_summary'
    }
    assert set(state['unchanged_decisions']) == {'inspection', 'spoils', 'water_accumulation', 'underground_utilities'}
    assert engine.get(sid)['conditions']['depth_ft'] == 4
    assert engine.get(sid)['conditions']['protective_system'] == 'none'
    assert [e['version'] for e in engine.history(sid)['state_events']] == [1, 2]
    assert decisions(state)['inspection']['evaluation_count'] == 1
    assert decisions(state)['protective_system']['evaluation_count'] == 2
    # Separate engine instance simulates restart and reads the same saved state.
    assert CRSEngine(engine.db_path).get(sid)['version'] == 2


def test_stale_version_fails_without_data_loss(engine):
    sid = create_from_text(engine, 'A 6-foot trench.')['scenario']['scenario_id']
    with pytest.raises(CRSVersionConflict):
        revise_from_text(engine, sid, 'The trench is now 4 feet deep.', 2)
    assert engine.get(sid)['version'] == 1


def test_hypothetical_not_applied_to_base(engine):
    sid = create_from_text(engine, 'A 6-foot trench.')['scenario']['scenario_id']
    with pytest.raises(CRSInputError, match='named scenario branch'):
        revise_from_text(engine, sid, 'What if it is 4 feet deep?', 1)
    assert engine.get(sid)['version'] == 1
    engine.branch(sid, 'what_if')
    alt = revise_from_text(engine, sid, 'What if it is 4 feet deep?', 1, branch='what_if')
    assert alt['scenario']['version'] == 2
    assert engine.get(sid)['conditions']['depth_ft'] == 6


def test_nl_flask_routes_auth_and_version_check(tmp_path, monkeypatch):
    pytest.importorskip('flask')
    from app import app
    monkeypatch.delenv('CRS_DATABASE_URL', raising=False)
    monkeypatch.delenv('CRS_REQUIRE_DURABLE_DB', raising=False)
    monkeypatch.setenv('CRS_DB_PATH', str(tmp_path / 'api-nl.sqlite3'))
    monkeypatch.setenv('CRS_API_KEY', 'local-test-key')
    client = app.test_client()
    endpoint = '/api/crs/nl/scenarios'
    assert client.post(endpoint, json={'text': 'A 6-foot trench.'}).status_code == 403
    hdr = {'Authorization': 'Bearer local-test-key'}
    r = client.post(endpoint, json={'text': 'Workers are inside a 6-foot trench without a protective system.'}, headers=hdr)
    assert r.status_code == 201
    sid = r.json['scenario']['scenario_id']
    assert r.json['scenario']['version'] == 1
    assert r.json['extraction']['conditions']['depth_ft'] == 6
    patch_url = f'{endpoint}/{sid}/messages'
    missing_version = client.post(patch_url, json={'text': 'Actually it is 4 feet deep'}, headers=hdr)
    assert missing_version.status_code == 400
    updated = client.post(patch_url, json={'text': 'Actually it is 4 feet deep', 'expected_version': 1}, headers=hdr)
    assert updated.status_code == 200
    assert updated.json['scenario']['version'] == 2
    assert len(updated.json['scenario']['reassessed_decisions']) == 3
    assert client.get(f'/api/crs/scenarios/{sid}', headers=hdr).json['conditions']['depth_ft'] == 4
