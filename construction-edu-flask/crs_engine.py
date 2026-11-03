"""CRS-RAG research prototype: versioned scoped states and explicit decision dependencies.

This is NOT a field-ready OSHA compliance service. Rule coverage is intentionally limited.
No LLM calls: the state and selective reassessment core are deterministic/testable.
"""
from __future__ import annotations

import json
import os
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4


def now():
    return datetime.now(timezone.utc).isoformat()


# The first curated, versioned OSHA knowledge units for Layer 4.
# Official source: OSHA 29 CFR 1926 Subpart P (reviewed 2026-11-02).
RULES = {
    'protective_system': {
        'title': 'Protection from cave-ins',
        'regulation': '29 CFR 1926.652(a)(1)',
        'url': 'https://www.osha.gov/laws-regs/regulations/standardnumber/1926/1926.652',
        'dependencies': ['employees_exposed', 'depth_ft', 'stable_rock',
                         'protective_system', 'competent_person_no_cave_in'],
    },
    'trench_egress': {
        'title': 'Means of egress from trench excavations',
        'regulation': '29 CFR 1926.651(c)(2)',
        'url': 'https://www.osha.gov/laws-regs/regulations/standardnumber/1926/1926.651',
        'dependencies': ['employees_exposed', 'is_trench', 'depth_ft', 'safe_egress_within_25ft'],
    },
    'spoils': {
        'title': 'Protection from excavated materials',
        'regulation': '29 CFR 1926.651(j)(2)',
        'url': 'https://www.osha.gov/laws-regs/regulations/standardnumber/1926/1926.651',
        'dependencies': ['employees_exposed', 'spoil_hazard', 'spoil_distance_ft', 'spoil_retained'],
    },
    'inspection': {
        'title': 'Competent-person inspections',
        'regulation': '29 CFR 1926.651(k)(1)',
        'url': 'https://www.osha.gov/laws-regs/regulations/standardnumber/1926/1926.651',
        'dependencies': ['employees_exposed', 'inspection_before_work',
                         'rain_event', 'inspection_after_rain'],
    },
    'assessed_rules_summary': {
        'title': 'Summary of assessed OSHA rules (not a safety certification)',
        'regulation': None, 'url': None, 'dependencies': [],
        'depends_on_decisions': ['protective_system', 'trench_egress', 'spoils', 'inspection'],
    },
}

BOOL_FIELDS = {
    'employees_exposed', 'stable_rock', 'competent_person_no_cave_in',
    'is_trench', 'safe_egress_within_25ft', 'spoil_hazard', 'spoil_retained',
    'inspection_before_work', 'rain_event', 'inspection_after_rain',
}
NUMBER_FIELDS = {'depth_ft', 'spoil_distance_ft'}
ENUM_FIELDS = {'protective_system': {'none', 'present_unverified', 'verified'}}
ALL_FIELDS = BOOL_FIELDS | NUMBER_FIELDS | set(ENUM_FIELDS)


class CRSInputError(ValueError):
    pass


class CRSNotFound(KeyError):
    pass


class CRSVersionConflict(Exception):
    pass


def validate_changes(changes):
    if not isinstance(changes, dict) or not changes:
        raise CRSInputError('conditions must be a nonempty JSON object')
    unknown = set(changes) - ALL_FIELDS
    if unknown:
        raise CRSInputError('Unsupported conditions: ' + ', '.join(sorted(unknown)))
    result = {}
    for key, val in changes.items():
        if val is None:
            result[key] = None  # Explicitly delete/mark unknown a previous value.
        elif key in BOOL_FIELDS:
            if not isinstance(val, bool):
                raise CRSInputError(key + ' must be boolean')
            result[key] = val
        elif key in NUMBER_FIELDS:
            if isinstance(val, bool) or not isinstance(val, (int, float)) or not 0 <= val <= 100000:
                raise CRSInputError(key + ' must be a nonnegative finite number <= 100000')
            # NaN fails the preceding comparison; Inf fails too.
            result[key] = float(val)
        elif key in ENUM_FIELDS:
            if not isinstance(val, str) or val not in ENUM_FIELDS[key]:
                raise CRSInputError(key + ' must be one of: ' + ', '.join(sorted(ENUM_FIELDS[key])))
            result[key] = val
    return result


def assess(decision_id, state):
    """Return (status, rationale); absent critical facts yield undetermined, never safe."""
    if decision_id == 'assessed_rules_summary':
        raise CRSInputError('Aggregate decision must be evaluated after its upstream decisions')
    get = state.get
    if get('employees_exposed') is None:
        return 'undetermined', 'Employee exposure is unknown; applicability requires clarification.'
    if not get('employees_exposed'):
        return 'not_applicable', 'No employee exposure is represented in the current scenario.'

    if decision_id == 'protective_system':
        depth = get('depth_ft')
        rock = get('stable_rock')
        protection = get('protective_system')
        examination = get('competent_person_no_cave_in')
        if rock is True:
            return 'compliant', 'Scenario specifies excavation entirely in stable rock; exception applies.'
        if depth is None:
            return 'undetermined', 'Excavation depth is missing.'
        if protection == 'verified':
            return 'compliant', 'Scenario indicates a protective system verified against applicable design requirements.'
        if protection == 'present_unverified':
            return 'undetermined', 'A protective system is present but its design adequacy is unverified.'
        if depth >= 5:
            if protection == 'none':
                if rock is False:
                    return 'noncompliant', 'Employees exposed at 5 feet or deeper without a protective system; stable-rock exception does not apply.'
                return 'undetermined', 'Stable-rock status is unknown; verify before concluding.'
            return 'undetermined', 'Protective-system presence and/or stable-rock status needs verification.'
        # Less than 5 ft: a competent-person examination must find no potential cave-in.
        if examination is True:
            return 'compliant', 'At less than 5 feet, competent-person examination found no indication of potential cave-in.'
        if examination is False and protection == 'none':
            return 'noncompliant', 'Cave-in potential was indicated, and no protective system is present.'
        return 'undetermined', 'For a depth below 5 feet, confirm the competent-person examination and protection.'

    if decision_id == 'trench_egress':
        if get('is_trench') is False:
            return 'not_applicable', 'The rule applies to trench excavations.'
        if get('is_trench') is None:
            return 'undetermined', 'Whether the excavation is a trench is unknown.'
        depth = get('depth_ft')
        if depth is None:
            return 'undetermined', 'Trench depth is unknown.'
        if depth < 4:
            return 'not_applicable', 'The trench is less than 4 feet deep.'
        if get('safe_egress_within_25ft') is True:
            return 'compliant', 'A safe means of egress is available within 25 feet of lateral travel.'
        if get('safe_egress_within_25ft') is False:
            return 'noncompliant', 'At 4 feet or deeper, no qualifying egress within 25 feet is provided.'
        return 'undetermined', 'Verify safe egress within 25 feet of lateral travel.'

    if decision_id == 'spoils':
        if get('spoil_hazard') is False:
            return 'not_applicable', 'No material/equipment hazard from falling or rolling spoils is represented.'
        if get('spoil_hazard') is None:
            return 'undetermined', 'Whether spoils/equipment create an edge hazard is unknown.'
        if get('spoil_retained') is True:
            return 'compliant', 'Scenario specifies adequate retaining devices for spoils/equipment.'
        distance = get('spoil_distance_ft')
        if distance is not None and distance >= 2:
            return 'compliant', 'Spoils/equipment are at least 2 feet from the excavation edge.'
        if distance is not None and distance < 2 and get('spoil_retained') is False:
            return 'noncompliant', 'Spoils/equipment are within 2 feet and adequate retaining devices are absent.'
        return 'undetermined', 'Need spoil distance and/or evidence of adequate retaining devices.'

    if decision_id == 'inspection':
        before = get('inspection_before_work')
        rain = get('rain_event')
        after = get('inspection_after_rain')
        if before is False:
            return 'noncompliant', 'Required competent-person inspection before work was not completed.'
        if rain is True and after is False:
            return 'noncompliant', 'A rainstorm occurred but the required subsequent inspection was not completed.'
        if before is None:
            return 'undetermined', 'Competent-person pre-work inspection is not confirmed.'
        if rain is None:
            return 'undetermined', 'Whether an additional rainstorm/hazard event occurred is unknown.'
        if rain is True and after is None:
            return 'undetermined', 'Confirm a competent-person inspection after the rainstorm.'
        return 'compliant', 'Reported pre-work and applicable post-rain inspections are completed.'

    raise CRSInputError('Unknown decision rule: ' + decision_id)


SCHEMA = '''
CREATE TABLE IF NOT EXISTS scenarios (
    scenario_id TEXT PRIMARY KEY, created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS branches (
    scenario_id TEXT NOT NULL, branch TEXT NOT NULL, parent_branch TEXT,
    fork_version INTEGER, state_json TEXT NOT NULL, version INTEGER NOT NULL,
    PRIMARY KEY (scenario_id, branch)
);
CREATE TABLE IF NOT EXISTS state_facts (
    state_id TEXT PRIMARY KEY, scenario_id TEXT NOT NULL, branch TEXT NOT NULL,
    key TEXT NOT NULL, value_json TEXT NOT NULL, version INTEGER NOT NULL,
    status TEXT NOT NULL, timestamp TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_active_facts ON state_facts (scenario_id, branch, key, status);
CREATE TABLE IF NOT EXISTS state_events (
    event_id TEXT PRIMARY KEY, scenario_id TEXT NOT NULL, branch TEXT NOT NULL,
    op TEXT NOT NULL, version INTEGER NOT NULL, changed_json TEXT NOT NULL, timestamp TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS decisions (
    scenario_id TEXT NOT NULL, branch TEXT NOT NULL, decision_id TEXT NOT NULL,
    status TEXT NOT NULL, rationale TEXT NOT NULL, evidence_json TEXT NOT NULL,
    evaluated_version INTEGER NOT NULL, evaluation_count INTEGER NOT NULL,
    PRIMARY KEY (scenario_id, branch, decision_id)
);
CREATE TABLE IF NOT EXISTS decision_dependencies (
    scenario_id TEXT NOT NULL, branch TEXT NOT NULL, decision_id TEXT NOT NULL,
    dependency_type TEXT NOT NULL, dependency_key TEXT NOT NULL,
    PRIMARY KEY (scenario_id, branch, decision_id, dependency_type, dependency_key)
);
CREATE INDEX IF NOT EXISTS ix_reverse_dependencies ON decision_dependencies
    (scenario_id, branch, dependency_type, dependency_key);
CREATE TABLE IF NOT EXISTS decision_events (
    event_id TEXT PRIMARY KEY, scenario_id TEXT NOT NULL, branch TEXT NOT NULL,
    decision_id TEXT NOT NULL, evaluated_version INTEGER NOT NULL,
    old_status TEXT, new_status TEXT NOT NULL, timestamp TEXT NOT NULL
);
-- Preserve the research catalog version actually consulted for each evaluated
-- decision; this remains distinct from the regulatory source's own revision.
CREATE TABLE IF NOT EXISTS decision_regulation_evidence (
    scenario_id TEXT NOT NULL, branch TEXT NOT NULL, decision_id TEXT NOT NULL,
    regulation_id TEXT NOT NULL, catalog_version TEXT NOT NULL,
    catalog_content_sha256 TEXT NOT NULL, catalog_checked_on TEXT NOT NULL,
    source_url TEXT NOT NULL,
    PRIMARY KEY (scenario_id, branch, decision_id, regulation_id)
);
'''


class _PostgresConnection:
    """Adapter for the deterministic core's small, fixed set of SQL operations.

    All queries are static trusted statements owned by this module.
    """
    def __init__(self, conn):
        self.conn = conn

    def executescript(self, schema):
        # Psycopg 3 accepts multiple SQL statements without query parameters.
        self.conn.execute(schema)

    def execute(self, sql, params=()):
        if sql.strip() == 'BEGIN IMMEDIATE':
            # Transaction-scoped advisory lock serializes revisions across replicas.
            return self.conn.execute('SELECT pg_advisory_xact_lock(1926652)')
        if sql.startswith('INSERT OR IGNORE INTO '):
            sql = sql.replace('INSERT OR IGNORE INTO ', 'INSERT INTO ', 1)
            sql += ' ON CONFLICT DO NOTHING'
        return self.conn.execute(sql.replace('?', '%s'), params)


class CRSEngine:
    def __init__(self, db_path=None):
        # Explicit db_path selects SQLite for tests and offline demonstrations.
        self.postgres_url = os.environ.get('CRS_DATABASE_URL') if db_path is None else None
        self.db_path = None if self.postgres_url else str(
            db_path or os.environ.get('CRS_DB_PATH', '/tmp/crs_rag_research.sqlite3'))
        if self.db_path == ':memory:':
            raise CRSInputError('Use a file-backed SQLite database for multi-request persistence')
        if self.db_path:
            Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        with self._db() as db:
            db.executescript(SCHEMA)

    @contextmanager
    def _db(self):
        if self.postgres_url:
            try:
                import psycopg
                from psycopg.rows import dict_row
            except ImportError as exc:
                raise RuntimeError('PostgreSQL backend requires psycopg[binary]') from exc
            # Never fall back to ephemeral SQLite if PostgreSQL is unreachable.
            with psycopg.connect(self.postgres_url, row_factory=dict_row,
                                 connect_timeout=10) as conn:
                yield _PostgresConnection(conn)
        else:
            db = sqlite3.connect(self.db_path, timeout=20)
            db.row_factory = sqlite3.Row
            db.execute('PRAGMA busy_timeout=20000')
            try:
                with db:
                    yield db
            finally:
                db.close()

    def _branch(self, db, scenario_id, branch):
        b = db.execute('SELECT * FROM branches WHERE scenario_id=? AND branch=?',
                       (scenario_id, branch)).fetchone()
        if b is None:
            raise CRSNotFound(f'Scenario/branch not found: {scenario_id}/{branch}')
        return b

    def _record_fact(self, db, sid, branch, key, value, version):
        db.execute("UPDATE state_facts SET status='superseded' WHERE scenario_id=? AND branch=? AND key=? AND status='active'",
                   (sid, branch, key))
        if value is not None:
            db.execute('INSERT INTO state_facts VALUES (?,?,?,?,?,?,?,?)',
                       (uuid4().hex, sid, branch, key, json.dumps(value), version, 'active', now()))

    def _evidence(self, db, sid, branch, decision_id):
        keys = RULES[decision_id]['dependencies']
        evidence = []
        for key in keys:
            row = db.execute('SELECT state_id, value_json, version FROM state_facts '
                             'WHERE scenario_id=? AND branch=? AND key=? AND status=?',
                             (sid, branch, key, 'active')).fetchone()
            evidence.append({'condition': key, 'state_id': row['state_id'] if row else None,
                             'value': json.loads(row['value_json']) if row else None,
                             'state_version': row['version'] if row else None})
        return evidence

    def _evaluate(self, db, sid, branch, version, state, ids):
        # Topological order: direct OSHA assessments before dependent summary decision.
        ids = sorted(ids, key=lambda d: bool(RULES[d].get('depends_on_decisions')))
        for decision_id in ids:
            rule = RULES[decision_id]
            if rule.get('depends_on_decisions'):
                upstream = [db.execute('SELECT status FROM decisions WHERE scenario_id=? AND branch=? AND decision_id=?',
                                       (sid, branch, name)).fetchone()
                            for name in rule['depends_on_decisions']]
                statuses = [d['status'] if d else 'undetermined' for d in upstream]
                if 'noncompliant' in statuses:
                    status, rationale = 'noncompliant', 'At least one assessed OSHA rule is noncompliant.'
                elif 'undetermined' in statuses:
                    status, rationale = 'undetermined', 'At least one assessed OSHA rule lacks sufficient evidence.'
                elif all(x == 'not_applicable' for x in statuses):
                    status, rationale = 'not_applicable', 'No included rule currently applies.'
                else:
                    status, rationale = 'compliant', 'All included rules were assessed compliant or not applicable; this is not a comprehensive safety assessment.'
            else:
                status, rationale = assess(decision_id, state)
            prev = db.execute('SELECT status, evaluation_count FROM decisions '
                              'WHERE scenario_id=? AND branch=? AND decision_id=?',
                              (sid, branch, decision_id)).fetchone()
            count = (prev['evaluation_count'] + 1) if prev else 1
            evidence = json.dumps(self._evidence(db, sid, branch, decision_id))
            db.execute('INSERT INTO decisions VALUES (?,?,?,?,?,?,?,?) '
                       'ON CONFLICT(scenario_id,branch,decision_id) DO UPDATE SET '
                       'status=excluded.status, rationale=excluded.rationale, '
                       'evidence_json=excluded.evidence_json, evaluated_version=excluded.evaluated_version, '
                       'evaluation_count=excluded.evaluation_count',
                       (sid, branch, decision_id, status, rationale, evidence, version, count))
            for key in rule['dependencies']:
                db.execute('INSERT OR IGNORE INTO decision_dependencies VALUES (?,?,?,?,?)',
                           (sid, branch, decision_id, 'condition', key))
            if rule['regulation']:
                db.execute('INSERT OR IGNORE INTO decision_dependencies VALUES (?,?,?,?,?)',
                           (sid, branch, decision_id, 'regulation', rule['regulation']))
                # Snapshot the catalog evidence used at assessment time.
                from crs.osha_retriever import get_regulation
                source = get_regulation(rule['regulation'])
                if source:
                    db.execute(
                        'INSERT INTO decision_regulation_evidence VALUES (?,?,?,?,?,?,?,?) '
                        'ON CONFLICT(scenario_id,branch,decision_id,regulation_id) DO UPDATE SET '
                        'catalog_version=excluded.catalog_version, '
                        'catalog_content_sha256=excluded.catalog_content_sha256, '
                        'catalog_checked_on=excluded.catalog_checked_on, '
                        'source_url=excluded.source_url',
                        (sid, branch, decision_id, source['id'], source['catalog_version'],
                         source['catalog_content_sha256'], source['catalog_checked_on'],
                         source['source_url']))
            for prior_id in rule.get('depends_on_decisions', []):
                db.execute('INSERT OR IGNORE INTO decision_dependencies VALUES (?,?,?,?,?)',
                           (sid, branch, decision_id, 'decision', prior_id))
            db.execute('INSERT INTO decision_events VALUES (?,?,?,?,?,?,?,?)',
                       (uuid4().hex, sid, branch, decision_id, version,
                        prev['status'] if prev else None, status, now()))

    def _view(self, db, sid, branch, reassessed=None):
        row = self._branch(db, sid, branch)
        facts = db.execute('SELECT state_id, key, value_json, version FROM state_facts '
                           'WHERE scenario_id=? AND branch=? AND status=? ORDER BY key',
                           (sid, branch, 'active')).fetchall()
        decisions = []
        for d in db.execute('SELECT * FROM decisions WHERE scenario_id=? AND branch=? ORDER BY decision_id',
                            (sid, branch)):
            rule = RULES[d['decision_id']]
            regulatory_evidence = []
            if rule['regulation']:
                saved_source = db.execute(
                    'SELECT * FROM decision_regulation_evidence WHERE '
                    'scenario_id=? AND branch=? AND decision_id=? AND regulation_id=?',
                    (sid, branch, d['decision_id'], rule['regulation'])).fetchone()
                entry = {'id': rule['regulation'], 'source_url': rule['url']}
                if saved_source:
                    from crs.osha_retriever import get_regulation
                    current = get_regulation(rule['regulation'])
                    entry.update({
                        'catalog_version_at_evaluation': saved_source['catalog_version'],
                        'catalog_content_sha256_at_evaluation': saved_source['catalog_content_sha256'],
                        'catalog_checked_on_at_evaluation': saved_source['catalog_checked_on'],
                        'catalog_changed_since_evaluation': (
                            current is None or
                            current['catalog_content_sha256'] != saved_source['catalog_content_sha256']),
                    })
                regulatory_evidence.append(entry)
            decisions.append({
                'decision_id': d['decision_id'], 'title': rule['title'],
                'status': d['status'], 'rationale': d['rationale'],
                'depends_on': rule['dependencies'],
                'depends_on_decisions': rule.get('depends_on_decisions', []),
                'evidence_states': json.loads(d['evidence_json']),
                'regulations': regulatory_evidence,
                'evaluated_version': d['evaluated_version'], 'evaluation_count': d['evaluation_count'],
            })
        return {
            'scenario_id': sid, 'branch': branch, 'parent_branch': row['parent_branch'],
            'version': row['version'], 'conditions': json.loads(row['state_json']),
            'active_states': [{'condition': r['key'], 'value': json.loads(r['value_json']),
                               'state_id': r['state_id'], 'version': r['version']} for r in facts],
            'decisions': decisions, 'reassessed_decisions': reassessed,
            'research_only': 'Prototype; incomplete OSHA coverage. Not a safety determination.'
        }

    def create(self, conditions):
        state = {k: v for k, v in validate_changes(conditions).items() if v is not None}
        sid = uuid4().hex
        with self._db() as db:
            db.execute('INSERT INTO scenarios VALUES (?,?)', (sid, now()))
            db.execute('INSERT INTO branches VALUES (?,?,?,?,?,?)',
                       (sid, 'base', None, None, json.dumps(state), 1))
            for key, value in state.items():
                self._record_fact(db, sid, 'base', key, value, 1)
            db.execute('INSERT INTO state_events VALUES (?,?,?,?,?,?,?)',
                       (uuid4().hex, sid, 'base', 'ADD', 1, json.dumps(state), now()))
            self._evaluate(db, sid, 'base', 1, state, sorted(RULES))
            return self._view(db, sid, 'base', sorted(RULES))

    def get(self, sid, branch='base'):
        with self._db() as db:
            return self._view(db, sid, branch)

    def revise(self, sid, changes, branch='base', expected_version=None):
        patch = validate_changes(changes)
        with self._db() as db:
            db.execute('BEGIN IMMEDIATE')
            row = self._branch(db, sid, branch)
            if expected_version is not None and expected_version != row['version']:
                raise CRSVersionConflict(f'Expected version {expected_version}, actual {row["version"]}')
            state = json.loads(row['state_json'])
            changed = {}
            for key, value in patch.items():
                if value is None:
                    if key in state:
                        changed[key] = {'previous': state.pop(key), 'current': None}
                elif key not in state or state[key] != value:
                    changed[key] = {'previous': state.get(key), 'current': value}
                    state[key] = value
            if not changed:
                return self._view(db, sid, branch, [])
            version = row['version'] + 1
            db.execute('UPDATE branches SET state_json=?, version=? WHERE scenario_id=? AND branch=?',
                       (json.dumps(state), version, sid, branch))
            for key, change in changed.items():
                self._record_fact(db, sid, branch, key, change['current'], version)
            db.execute('INSERT INTO state_events VALUES (?,?,?,?,?,?,?)',
                       (uuid4().hex, sid, branch, 'REVISE', version, json.dumps(changed), now()))
            placeholders = ','.join('?' for _ in changed)
            affected = db.execute(
                'SELECT DISTINCT decision_id FROM decision_dependencies '
                'WHERE scenario_id=? AND branch=? AND dependency_type=? '
                f'AND dependency_key IN ({placeholders}) ORDER BY decision_id',
                (sid, branch, 'condition', *changed.keys())
            ).fetchall()
            ids = [r['decision_id'] for r in affected]
            # Traverse reverse decision dependencies for transitive invalidation.
            pending = list(ids)
            while pending:
                parent = pending.pop(0)
                children = db.execute(
                    'SELECT decision_id FROM decision_dependencies WHERE '
                    'scenario_id=? AND branch=? AND dependency_type=? AND dependency_key=?',
                    (sid, branch, 'decision', parent)).fetchall()
                for child in children:
                    if child['decision_id'] not in ids:
                        ids.append(child['decision_id'])
                        pending.append(child['decision_id'])
            ids = sorted(ids)
            self._evaluate(db, sid, branch, version, state, ids)
            result = self._view(db, sid, branch, ids)
            result['changed_conditions'] = changed
            result['unchanged_decisions'] = [r for r in RULES if r not in ids]
            return result

    def branch(self, sid, name, from_branch='base'):
        if not isinstance(name, str) or not name or len(name) > 50 or not all(c.isalnum() or c in '-_' for c in name) or name == 'base':
            raise CRSInputError('branch name must be 1-50 alphanumeric, dash, or underscore characters (not base)')
        with self._db() as db:
            db.execute('BEGIN IMMEDIATE')
            source = self._branch(db, sid, from_branch)
            if db.execute('SELECT 1 FROM branches WHERE scenario_id=? AND branch=?', (sid, name)).fetchone():
                raise CRSInputError('Branch already exists')
            state = json.loads(source['state_json'])
            db.execute('INSERT INTO branches VALUES (?,?,?,?,?,?)',
                       (sid, name, from_branch, source['version'], json.dumps(state), 1))
            for key, value in state.items():
                self._record_fact(db, sid, name, key, value, 1)
            db.execute('INSERT INTO state_events VALUES (?,?,?,?,?,?,?)',
                       (uuid4().hex, sid, name, 'BRANCH', 1,
                        json.dumps({'from_branch': from_branch, 'from_version': source['version']}), now()))
            self._evaluate(db, sid, name, 1, state, sorted(RULES))
            return self._view(db, sid, name, sorted(RULES))

    def history(self, sid, branch='base'):
        with self._db() as db:
            self._branch(db, sid, branch)
            events = db.execute('SELECT op, version, changed_json, timestamp FROM state_events '
                                'WHERE scenario_id=? AND branch=? ORDER BY version',
                                (sid, branch)).fetchall()
            decisions = db.execute('SELECT decision_id, evaluated_version, old_status, new_status, timestamp '
                                   'FROM decision_events WHERE scenario_id=? AND branch=? '
                                   'ORDER BY evaluated_version, decision_id',
                                   (sid, branch)).fetchall()
            return {'scenario_id': sid, 'branch': branch,
                    'state_events': [{'operation': e['op'], 'version': e['version'],
                                      'changes': json.loads(e['changed_json']),
                                      'timestamp': e['timestamp']} for e in events],
                    'decision_events': [dict(d) for d in decisions]}
