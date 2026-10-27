"""Sanitized Flask website/API demo. No AI keys or student data."""
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4
from flask import Flask, jsonify, request, send_from_directory

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

@app.errorhandler(413)
def too_large(_):
    return jsonify({'error': 'Request body is too large'}), 413
