"""Run the dependency-tracking excavation demo without Flask or an LLM."""
from pathlib import Path
from tempfile import TemporaryDirectory
from crs_engine import CRSEngine


def print_decisions(view):
    print(f"Branch={view['branch']} Version={view['version']}")
    for d in view['decisions']:
        print(f"  {d['decision_id']:24} {d['status']:14} evaluated={d['evaluation_count']}x")


with TemporaryDirectory() as tmp:
    engine = CRSEngine(Path(tmp) / 'research.sqlite3')
    conditions = {
        'employees_exposed': True, 'depth_ft': 6, 'stable_rock': False,
        'protective_system': 'none', 'competent_person_no_cave_in': False,
        'is_trench': True, 'safe_egress_within_25ft': True,
        'spoil_hazard': True, 'spoil_distance_ft': 3, 'spoil_retained': False,
        'inspection_before_work': True, 'rain_event': False,
    }
    print('1. Create scenario:')
    first = engine.create(conditions)
    sid = first['scenario_id']
    print_decisions(first)
    print('\n2. Change excavation depth from 6 ft to 4 ft:')
    update = engine.revise(sid, {'depth_ft': 4}, expected_version=1)
    print('Reassessed:', update['reassessed_decisions'])
    print('Not recomputed:', update['unchanged_decisions'])
    print_decisions(update)
    print('\n3. Competent-person examination finds no cave-in indication:')
    update = engine.revise(sid, {'competent_person_no_cave_in': True}, expected_version=2)
    print('Reassessed:', update['reassessed_decisions'])
    print_decisions(update)
    print('\n4. Hypothetical branch:')
    engine.branch(sid, 'hypothetical')
    engine.revise(sid, {'spoil_distance_ft': 1, 'spoil_retained': False}, branch='hypothetical')
    print('Base spoils:', [x for x in engine.get(sid)['decisions'] if x['decision_id'] == 'spoils'][0]['status'])
    print('Hypothetical spoils:', [x for x in engine.get(sid, 'hypothetical')['decisions'] if x['decision_id'] == 'spoils'][0]['status'])
    print('\nPersisted audit events:', len(engine.history(sid)['state_events']))
