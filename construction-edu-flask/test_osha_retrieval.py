"""Layer 4: selected OSHA source retrieval, matching, version evidence."""
import json
import pytest

from crs.osha_retriever import (
    CATALOG_PATH, _catalog, catalogue_versions, get_regulation, retrieve_osha,
)
from crs_engine import CRSEngine
from crs.state_resolver import create_from_text, revise_from_text


def test_catalog_contains_official_citations_and_catalog_versions():
    meta = catalogue_versions()
    assert meta['catalog_version'] == 'osha-subpart-p-excavation-v2'
    assert meta['source_is_live'] is False
    assert meta['total_catalog_entries'] >= 10
    by_id = {x['id']: x for x in meta['citations']}
    for citation in (
        '29 CFR 1926.652(a)(1)', '29 CFR 1926.651(c)(2)',
        '29 CFR 1926.651(j)(2)', '29 CFR 1926.651(k)(1)',
        '29 CFR 1926.651(b)(1)', '29 CFR 1926.651(g)(1)(i)',
        '29 CFR 1926.651(h)(1)',
    ):
        item = by_id[citation]
        assert item['source_url'].startswith('https://www.osha.gov/')
        assert len(item['catalog_content_sha256']) == 64


def test_search_retrieves_excavation_requirements_by_conditions():
    result = retrieve_osha(conditions={
        'is_trench': True, 'depth_ft': 6,
        'protective_system': 'none', 'employees_exposed': True,
    })
    ids = {x['id'] for x in result['results']}
    assert '29 CFR 1926.652(a)(1)' in ids
    assert '29 CFR 1926.651(c)(2)' in ids
    assert '29 CFR 1926.651(b)(1)' not in ids
    assert '29 CFR 1926.651(h)(1)' not in ids
    assert result['source'].startswith('OSHA')
    assert 'outdated' in result['warning']


def test_text_search_finds_utilities_and_water():
    utilities = retrieve_osha(query='Before digging the utility crew encountered a buried water line')
    assert '29 CFR 1926.651(b)(1)' in {x['id'] for x in utilities['results']}
    water = retrieve_osha(query='Standing water is accumulating in the excavation')
    got = {x['id'] for x in water['results']}
    assert '29 CFR 1926.651(h)(1)' in got


def test_text_search_atmosphere_is_not_assessed():
    resp = retrieve_osha(query='Hazardous atmosphere and oxygen deficiency near a landfill')
    hits = {x['id']: x for x in resp['results']}
    assert '29 CFR 1926.651(g)(1)(i)' in hits
    assert hits['29 CFR 1926.651(g)(1)(i)']['assessment_supported'] is False
    assert 'source_is_live' in hits['29 CFR 1926.651(g)(1)(i)']
    assert hits['29 CFR 1926.651(g)(1)(i)']['source_is_live'] is False


@pytest.mark.parametrize('kwargs', [
    {},
    {'query': 123},
    {'conditions': 'trench'},
    {'query': 'trench', 'limit': 0},
    {'query': 'trench', 'limit': True},
    {'query': 'trench', 'limit': 200},
])
def test_search_input_validation(kwargs):
    with pytest.raises(ValueError):
        retrieve_osha(**kwargs)


def test_retrieval_deterministic_and_limited():
    x = retrieve_osha(query='A trench excavation with spoil piles', limit=2)
    y = retrieve_osha(query='A trench excavation with spoil piles', limit=2)
    assert x == y
    assert len(x['results']) == 2
    assert x['total_matches'] >= 2
    assert x['results'][0]['relevance_score'] >= x['results'][1]['relevance_score']


def test_assessments_record_catalog_version_at_evaluation(tmp_path):
    engine = CRSEngine(tmp_path / 'source_evidence.sqlite3')
    scenario = engine.create({
        'employees_exposed': True,
        'is_trench': True,
        'depth_ft': 6,
        'protective_system': 'none',
    })
    sid = scenario['scenario_id']
    protective = next(x for x in scenario['decisions'] if x['decision_id'] == 'protective_system')
    cite = protective['regulations'][0]
    assert cite['id'] == '29 CFR 1926.652(a)(1)'
    assert cite['catalog_version_at_evaluation'] == 'osha-subpart-p-excavation-v2'
    assert len(cite['catalog_content_sha256_at_evaluation']) == 64
    assert cite['catalog_changed_since_evaluation'] is False
    assert CRSEngine(tmp_path / 'source_evidence.sqlite3').get(sid)['decisions'][0]['decision_id']
    changed = engine.revise(sid, {'depth_ft': 4}, expected_version=1)
    untouched = next(x for x in changed['decisions'] if x['decision_id'] == 'inspection')
    # Decisions without changed dependencies have not been evaluated again.
    assert untouched['evaluation_count'] == 1
    assert next(x for x in changed['decisions'] if x['decision_id'] == 'protective_system')['evaluation_count'] == 2


def test_catalog_changes_flag_prior_decisions_without_claiming_reassessment(tmp_path, monkeypatch):
    engine = CRSEngine(tmp_path / 'catalog-drift.sqlite3')
    original = engine.create({'depth_ft': 6, 'is_trench': True})
    sid = original['scenario_id']
    source = get_regulation('29 CFR 1926.652(a)(1)')
    assert source is not None
    # Simulate revised research catalog loaded in a future container image.
    snap = json.loads(CATALOG_PATH.read_text(encoding='utf-8'))
    for row in snap['regulations']:
        if row['id'] == '29 CFR 1926.652(a)(1)':
            row['summary'] += ' Catalog correction for drift test.'
    other = tmp_path / 'revised.json'
    other.write_text(json.dumps(snap), encoding='utf-8')
    import crs.osha_retriever as retriever
    monkeypatch.setattr(retriever, 'CATALOG_PATH', other)
    _catalog.cache_clear()
    try:
        later = engine.get(sid)
        protective = next(x for x in later['decisions'] if x['decision_id'] == 'protective_system')
        assert protective['regulations'][0]['catalog_changed_since_evaluation'] is True
        assert protective['evaluation_count'] == 1
    finally:
        _catalog.cache_clear()


def test_nl_response_has_retrieved_sources(tmp_path):
    engine = CRSEngine(tmp_path / 'nl-retrieval.sqlite3')
    a = create_from_text(engine, 'Workers are inside a 6-foot trench without a protective system.')
    found = {x['id'] for x in a['osha_retrieval']['results']}
    assert '29 CFR 1926.652(a)(1)' in found
    sid = a['scenario']['scenario_id']
    b = revise_from_text(engine, sid, 'Actually, the trench is only 4 feet deep.', 1)
    assert b['scenario']['version'] == 2
    assert '29 CFR 1926.651(c)(2)' in {x['id'] for x in b['osha_retrieval']['results']}
    assert set(b['scenario']['unchanged_decisions']) == {'inspection', 'spoils', 'water_accumulation', 'underground_utilities'}


def test_flask_osha_endpoints_authorized_and_integrated(tmp_path, monkeypatch):
    from app import app
    monkeypatch.delenv('CRS_DATABASE_URL', raising=False)
    monkeypatch.delenv('CRS_REQUIRE_DURABLE_DB', raising=False)
    monkeypatch.setenv('CRS_DB_PATH', str(tmp_path / 'osha-api.sqlite3'))
    monkeypatch.setenv('CRS_API_KEY', 'test-only-api-key')
    client = app.test_client()
    search = '/api/crs/osha/search'
    assert client.post(search, json={'query': 'water'}).status_code == 403
    hdr = {'Authorization': 'Bearer test-only-api-key'}
    assert client.post(search, json={'query': 'water'}, headers=hdr).status_code == 200
    assert client.post(search, json={}, headers=hdr).status_code == 400
    assert client.post(search, json={'query': 'water', 'limit': 100}, headers=hdr).status_code == 400
    assert client.get('/api/crs/osha/catalog', headers=hdr).json['total_catalog_entries'] >= 10
    created = client.post('/api/crs/nl/scenarios',
                          json={'text': 'Workers are inside a 6-foot trench without a protective system.'},
                          headers=hdr)
    assert created.status_code == 201
    assert created.json['osha_retrieval']['results']
    sid = created.json['scenario']['scenario_id']
    detail = client.get(f'/api/crs/scenarios/{sid}/osha', headers=hdr)
    assert detail.status_code == 200
    assert detail.json['scenario_version'] == 1
    assert '29 CFR 1926.652(a)(1)' in {r['id'] for r in detail.json['retrieval']['results']}
    assert detail.json['assessed_regulations']
    assert client.get('/api/crs/scenarios/no-such-scenario/osha', headers=hdr).status_code == 404
