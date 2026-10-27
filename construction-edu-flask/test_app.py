from app import app

def test_home_and_assets():
    client = app.test_client()
    assert client.get('/').status_code == 200
    assert client.get('/styles.css').status_code == 200
    assert client.get('/app.js').status_code == 200

def test_apis():
    client = app.test_client()
    assert client.get('/api/health').json['status'] == 'ok'
    for path in ('/api/prompt', '/api/chat', '/chat', '/cee_chat'):
        r = client.post(path, json={'prompt': 'What is BIM?'})
        assert r.status_code == 200
        assert r.json['mode'] == 'demo'
        assert 'not an AI-generated answer' in r.json['response']
    assert client.post('/api/prompt', json={'prompt': ''}).status_code == 400
    assert client.post('/api/prompt', json={'prompt': 'x'*2001}).status_code == 400
    assert client.post('/api/prompt', data='hello').status_code == 415
