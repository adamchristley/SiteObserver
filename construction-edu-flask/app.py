"""Flask demo plus opt-in, API-key-protected CRS-RAG research endpoints.

Do not deploy the SQLite prototype as a production or field-safety service.
"""
from datetime import datetime, timezone
from functools import wraps
from pathlib import Path
from uuid import uuid4
import hmac
import os

from flask import Flask, jsonify, request, send_from_directory
from crs_engine import (CRSEngine, CRSInputError, CRSNotFound, CRSVersionConflict,
                        RULES)

WEB = Path(__file__).resolve().parent / 'prompt-web'
if not WEB.is_dir():
    WEB = Path(__file__).resolve().parent.parent / 'prompt-web'
app = Flask(__name__)
app.config['MAX_CONTENT_LENGTH'] = 8192


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
        if not secret or not hmac.compare_digest(token, 'Bearer ' + secret):
            return jsonify({'error': 'CRS research endpoint is disabled or unauthorized'}), 403
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


@app.get('/api/crs/regulations')
@crs_protected
def regulations(engine):
    del engine
    return jsonify(RULES)


@app.post('/api/crs/scenarios')
@crs_protected
def create_scenario(engine):
    payload = json_payload()
    return jsonify(engine.create(payload.get('conditions'))), 201


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
