"""Flask demo plus opt-in, API-key-protected CRS-RAG research endpoints.

Do not deploy the SQLite prototype as a production or field-safety service.
"""
from datetime import datetime, timezone
from functools import wraps
from pathlib import Path
from uuid import uuid4
import hmac
import os
import secrets

from flask import Flask, jsonify, request, send_from_directory, session
from crs.pipeline import create_from_text, revise_from_text
from crs.assistant import CRSAssistant, model_available
from crs.document_rag import OSHAIndex, get_index
from crs.osha_retriever import retrieve_osha, catalogue_versions
from crs_engine import (CRSEngine, CRSInputError, CRSNotFound, CRSVersionConflict,
                        RULES, validate_changes)

WEB = Path(__file__).resolve().parent / 'prompt-web'
if not WEB.is_dir():
    WEB = Path(__file__).resolve().parent.parent / 'prompt-web'
app = Flask(__name__)
app.config['MAX_CONTENT_LENGTH'] = 16384
app.secret_key = os.environ.get('CRS_WEB_SESSION_KEY') or None
app.config.update(SESSION_COOKIE_HTTPONLY=True, SESSION_COOKIE_SECURE=True,
                  SESSION_COOKIE_SAMESITE='Strict', PERMANENT_SESSION_LIFETIME=3600)


@app.after_request
def secure(response):
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['X-Frame-Options'] = 'DENY'
    response.headers['Referrer-Policy'] = 'no-referrer'
    response.headers['Content-Security-Policy'] = (
        "default-src 'self'; script-src 'self'; style-src 'self'; "
        "img-src 'self' data:; connect-src 'self'; object-src 'none'; "
        "frame-ancestors 'none'; base-uri 'self'; form-action 'self'"
    )
    response.headers['Cache-Control'] = 'no-store'
    return response


@app.get('/')
def home():
    return send_from_directory(WEB, 'index.html')


@app.get('/app.js')
def js():
    return send_from_directory(WEB, 'app.js')


@app.get('/styles.css')
def css():
    return send_from_directory(WEB, 'styles.css')


@app.get('/api/health')
@app.get('/health')
def health():
    return jsonify({'status': 'ok', 'mode': 'demo', 'service': 'construction-education-flask'})


@app.post('/api/prompt')
@app.post('/api/chat')
@app.post('/chat')
@app.post('/cee_chat')
def prompt():
    if not request.is_json:
        return jsonify({'error': 'Content-Type must be application/json'}), 415
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        return jsonify({'error': 'Send a JSON object'}), 400
    message = payload.get('prompt', payload.get('user_message'))
    if not isinstance(message, str):
        return jsonify({'error': 'prompt must be text'}), 400
    message = message.strip()
    if not message or len(message) > 2000:
        return jsonify({'error': 'Prompt must contain 1 to 2,000 characters'}), 400
    return jsonify({
        'mode': 'demo',
        'response': (
            'The Azure-hosted Flask API received your prompt successfully. '
            'This is a demo acknowledgment, not an AI-generated answer. '
            'The next milestone is to connect the authorized Azure OpenAI '
            'and course-document retrieval services.'
        ),
        'requestId': uuid4().hex[:12],
        'timestamp': datetime.now(timezone.utc).isoformat(),
        'promptLength': len(message),
    })


def crs_protected(route):
    @wraps(route)
    def wrapper(*args, **kwargs):
        secret = os.environ.get('CRS_API_KEY', '')
        token = request.headers.get('Authorization', '')
        # Feature disabled unless explicitly configured. Do not expose user scenario data unauthenticated.
        bearer_ok = bool(secret and hmac.compare_digest(token, 'Bearer ' + secret))
        web_ok = bool(app.secret_key and session.get('crs_research'))
        if not bearer_ok and not web_ok:
            return jsonify({'error': 'CRS research endpoint is disabled or unauthorized'}), 403
        if web_ok and not bearer_ok and request.method in ('POST', 'PATCH', 'PUT', 'DELETE'):
            if not hmac.compare_digest(str(session.get('csrf', '')),
                                       request.headers.get('X-CSRF-Token', '')):
                return jsonify({'error': 'CSRF token required'}), 403
        if os.environ.get('CRS_REQUIRE_DURABLE_DB') == '1' and not os.environ.get('CRS_DATABASE_URL'):
            return jsonify({'error': 'Durable CRS database must be configured'}), 503
        try:
            return route(CRSEngine(), *args, **kwargs)
        except CRSInputError as exc:
            return jsonify({'error': str(exc)}), 400
        except CRSNotFound as exc:
            return jsonify({'error': str(exc)}), 404
        except CRSVersionConflict as exc:
            return jsonify({'error': str(exc)}), 409
    return wrapper


def json_payload():
    if not request.is_json or not isinstance(request.get_json(silent=True), dict):
        raise CRSInputError('JSON object required')
    return request.get_json()


@app.post('/api/crs/web/login')
def web_login():
    password = os.getenv('CRS_WEB_PASSWORD', '')
    if not password or not app.secret_key:
        return jsonify({'error': 'Web login is disabled until server-side secrets are configured'}), 503
    payload = json_payload()
    submitted = payload.get('password', '')
    if not isinstance(submitted, str) or not hmac.compare_digest(password, submitted):
        return jsonify({'error': 'Invalid credentials'}), 403
    session.clear()
    session.permanent = True
    session['crs_research'] = True
    session['csrf'] = secrets.token_urlsafe(32)
    return jsonify({'authenticated': True, 'csrf_token': session['csrf']})


@app.get('/api/crs/web/session')
def web_session():
    ok = bool(app.secret_key and session.get('crs_research'))
    return jsonify({'authenticated': ok, 'csrf_token': session.get('csrf') if ok else None})


@app.post('/api/crs/web/logout')
def web_logout():
    if not session.get('crs_research') or not hmac.compare_digest(
            str(session.get('csrf', '')), request.headers.get('X-CSRF-Token', '')):
        return jsonify({'error': 'Unauthorized'}), 403
    session.clear()
    return jsonify({'authenticated': False})


@app.get('/api/crs/assistant/status')
@crs_protected
def assistant_status(engine):
    del engine
    return jsonify({'corpus': get_index().status(), 'model_configured': model_available(),
                    'human_review_required': True})


@app.get('/api/crs/assistant/search')
@crs_protected
def assistant_search(engine):
    """Research-only, subpart-filterable search across all indexed Part 1926."""
    del engine
    try:
        raw_limit = request.args.get('limit', '8')
        limit = int(raw_limit)
        result = get_index().search(
            request.args.get('q', ''),
            limit=limit,
            subpart=request.args.get('subpart') or None)
    except (ValueError, TypeError) as exc:
        raise CRSInputError(str(exc)) from exc
    return jsonify(result)


@app.post('/api/crs/assistant')
@crs_protected
def assistant_message(engine):
    payload = json_payload()
    response = CRSAssistant(engine, index=get_index()).analyze(
        payload.get('text'), payload.get('scenario_id'),
        payload.get('branch', 'base'), payload.get('expected_version'))
    return jsonify(response), (201 if response.get('scenario') and not payload.get('scenario_id') else 200)


@app.get('/api/crs/assistant/<sid>/history')
@crs_protected
def assistant_history(engine, sid):
    return jsonify(CRSAssistant(engine, index=get_index()).history(sid, request.args.get('branch', 'base')))


@app.get('/api/crs/assistant/<sid>/graph')
@crs_protected
def assistant_graph(engine, sid):
    return jsonify(CRSAssistant(engine, index=get_index()).graph(sid, request.args.get('branch', 'base')))


@app.get('/api/crs/regulations')
@crs_protected
def regulations(engine):
    del engine
    return jsonify(RULES)


@app.get('/api/crs/osha/catalog')
@crs_protected
def osha_catalog(engine):
    del engine
    return jsonify(catalogue_versions())


@app.post('/api/crs/osha/search')
@crs_protected
def osha_search(engine):
    del engine
    payload = json_payload()
    query = payload.get('query', '')
    conditions = payload.get('conditions') or {}
    if conditions:
        conditions = validate_changes(conditions)
    try:
        result = retrieve_osha(query=query, conditions=conditions, limit=payload.get('limit', 12))
    except ValueError as exc:
        raise CRSInputError(str(exc)) from exc
    return jsonify(result)


@app.get('/api/crs/scenarios/<sid>/osha')
@crs_protected
def osha_for_scenario(engine, sid):
    branch = request.args.get('branch', 'base')
    scenario = engine.get(sid, branch)
    try:
        matching = retrieve_osha(
            query=request.args.get('q', ''),
            conditions=scenario['conditions'],
            limit=12)
    except ValueError as exc:
        raise CRSInputError(str(exc)) from exc
    return jsonify({
        'scenario_id': sid,
        'branch': branch,
        'scenario_version': scenario['version'],
        'retrieval': matching,
        'assessed_regulations': [
            {'decision_id': d['decision_id'], 'status': d['status'],
             'regulations': d['regulations']} for d in scenario['decisions']
            if d['regulations']
        ],
        'warning': 'Other retrieved entries are not yet evaluated by the rule engine.',
    })


@app.post('/api/crs/scenarios')
@crs_protected
def create_scenario(engine):
    payload = json_payload()
    return jsonify(engine.create(payload.get('conditions'))), 201


@app.post('/api/crs/nl/scenarios')
@crs_protected
def create_nl_scenario(engine):
    """Extract explicit facts from English and create a versioned scenario."""
    payload = json_payload()
    return jsonify(create_from_text(engine, payload.get('text'))), 201


@app.post('/api/crs/nl/scenarios/<sid>/messages')
@crs_protected
def revise_nl_scenario(engine, sid):
    """Apply an English correction; optimistic version check prevents stale updates."""
    payload = json_payload()
    return jsonify(revise_from_text(engine, sid, payload.get('text'),
                                    payload.get('expected_version'),
                                    payload.get('branch', 'base')))


@app.get('/api/crs/scenarios/<sid>')
@crs_protected
def get_scenario(engine, sid):
    return jsonify(engine.get(sid, request.args.get('branch', 'base')))


@app.patch('/api/crs/scenarios/<sid>/conditions')
@crs_protected
def update_conditions(engine, sid):
    payload = json_payload()
    version = payload.get('expected_version')
    if version is not None and (type(version) is not int or version < 1):
        raise CRSInputError('expected_version must be a positive integer')
    return jsonify(engine.revise(sid, payload.get('changes'),
                                 payload.get('branch', 'base'), version))


@app.post('/api/crs/scenarios/<sid>/branches')
@crs_protected
def new_branch(engine, sid):
    payload = json_payload()
    return jsonify(engine.branch(sid, payload.get('name'), payload.get('from_branch', 'base'))), 201


@app.get('/api/crs/scenarios/<sid>/history')
@crs_protected
def get_history(engine, sid):
    return jsonify(engine.history(sid, request.args.get('branch', 'base')))


@app.errorhandler(413)
def too_large(_):
    return jsonify({'error': 'Request body is too large'}), 413
