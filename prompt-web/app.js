'use strict';
const $ = (s) => document.querySelector(s);
const state = { csrf: null, scenario: null, branch: 'base', loading: false };
const D = (tag, className, text) => {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined && text !== null) node.textContent = String(text);
  return node;
};
async function api(path, method = 'GET', body) {
  const headers = { 'Accept': 'application/json' };
  if (method !== 'GET') {
    headers['Content-Type'] = 'application/json';
    if (state.csrf) headers['X-CSRF-Token'] = state.csrf;
  }
  const response = await fetch(path, {
    method, headers, credentials: 'same-origin', cache: 'no-store',
    body: body === undefined ? undefined : JSON.stringify(body)
  });
  let data;
  try { data = await response.json(); } catch { throw new Error('Invalid server response'); }
  if (!response.ok) throw new Error(data.error || 'Request failed: HTTP ' + response.status);
  return data;
}
function alertError(message) {
  $('#app-error').textContent = message || '';
}
function loggedIn(yes) {
  $('#login-screen').hidden = yes;
  $('#workspace').hidden = !yes;
  $('#logout').hidden = !yes;
  $('#connection').textContent = yes ? 'Secure session active' : 'Sign in required';
  if (yes) loadStatus();
}
async function boot() {
  try {
    const data = await api('/api/crs/web/session');
    state.csrf = data.csrf_token;
    loggedIn(Boolean(data.authenticated));
  } catch {
    loggedIn(false);
    $('#login-error').textContent = 'Unable to connect to the research service.';
  }
}
$('#login-form').addEventListener('submit', async (event) => {
  event.preventDefault();
  $('#login-error').textContent = '';
  try {
    const result = await api('/api/crs/web/login', 'POST', { password: $('#password').value });
    $('#password').value = '';
    state.csrf = result.csrf_token;
    loggedIn(true);
  } catch (error) {
    $('#login-error').textContent = error.message;
  }
});
$('#logout').addEventListener('click', async () => {
  try { await api('/api/crs/web/logout', 'POST', {}); } catch {}
  state.csrf = null;
  clearScenario();
  loggedIn(false);
});
async function loadStatus() {
  try {
    const s = await api('/api/crs/assistant/status');
    $('#corpus-state').textContent = s.corpus.ready ? 'READY' : 'NOT INDEXED';
    $('#model-state').textContent = s.model_configured ? 'AZURE LLM' : 'RULE BASED';
    $('#corpus-detail').textContent = s.corpus.ready ?
      s.corpus.source_pages + ' official source pages, ' + s.corpus.chunks + ' indexed passages. Snapshot: ' + (s.corpus.retrieved_at || 'unknown') :
      'Official source-text archive is not installed. Only the small curated reference catalog is available.';
  } catch (err) { alertError(err.message); }
}
function clearScenario() {
  state.scenario = null;
  state.branch = 'base';
  $('#branch-select').replaceChildren(new Option('Base facts', 'base'));
  $('#scenario-id').textContent = 'New scenario';
  $('#version').textContent = 'No state yet';
  $('#messages').replaceChildren();
  const empty = D('div', 'empty-chat');
  empty.append(D('h3', '', 'Start with a site description.'),
               D('p', '', 'Provide known excavation facts, then submit updates to inspect what changes.'));
  $('#messages').append(empty);
  for (const name of ['decisions', 'evidence', 'graph', 'history']) {
    $('#' + name).replaceChildren(D('p', 'muted', 'No scenario data yet.'));
  }
  $('#conversation-state').textContent = 'Ready to begin';
  alertError('');
}
$('#reset-scenario').addEventListener('click', clearScenario);
$('#branch-select').addEventListener('change', async (event) => {
  state.branch = event.target.value;
  if (state.scenario) {
    try {
      const view = await api('/api/crs/scenarios/' + state.scenario.scenario_id + '?branch=' + encodeURIComponent(state.branch));
      state.scenario = view;
      renderScenario(view);
      await refreshDetails();
    } catch (err) { alertError(err.message); }
  }
});
$('#create-branch').addEventListener('click', async () => {
  if (!state.scenario) return alertError('Create a scenario before forking it.');
  const name = $('#branch-name').value.trim();
  if (!/^[a-zA-Z0-9_-]{1,40}$/.test(name) || name === 'base') return alertError('Choose a branch name of 1 to 40 letters, digits, dashes or underscores.');
  try {
    const view = await api('/api/crs/scenarios/' + state.scenario.scenario_id + '/branches', 'POST',
      { name, from_branch: state.branch });
    $('#branch-select').add(new Option(name, name));
    $('#branch-select').value = name;
    $('#branch-name').value = '';
    state.branch = name;
    state.scenario = view;
    renderScenario(view);
    await refreshDetails();
    alertError('');
  } catch (err) { alertError(err.message); }
});
function appendMessage(kind, label, body, status) {
  if ($('#messages').querySelector('.empty-chat')) $('#messages').replaceChildren();
  const item = D('article', 'chat-bubble ' + kind);
  const heading = D('div', 'bubble-heading', label);
  if (status) heading.append(D('span', 'assessment-tag', status));
  item.append(heading, D('p', '', body || 'No response provided.'));
  $('#messages').append(item);
  $('#messages').scrollTop = $('#messages').scrollHeight;
}
function renderScenario(view) {
  $('#scenario-id').textContent = view.scenario_id || 'New scenario';
  $('#version').textContent = 'Version ' + view.version + ' · ' + state.branch;
  const decisions = $('#decisions');
  decisions.replaceChildren();
  for (const item of (view.decisions || [])) {
    const box = D('article', 'decision');
    const heading = D('div', 'decision-head');
    heading.append(D('strong', '', item.decision_id.replaceAll('_', ' ')),
                   D('span', 'status ' + String(item.status).toLowerCase(), item.status));
    box.append(heading, D('p', '', item.rationale || 'Not determined'));
    box.append(D('small', '', 'Evaluated ' + item.evaluation_count + ' time(s); version ' + item.evaluated_version));
    decisions.append(box);
  }
  if (view.reassessed_decisions?.length) {
    $('#conversation-state').textContent = 'Reassessed: ' + view.reassessed_decisions.join(', ');
  } else {
    $('#conversation-state').textContent = 'Version ' + view.version + ' saved';
  }
}
function renderEvidence(list) {
  const root = $('#evidence');
  root.replaceChildren();
  if (!list?.length) return root.append(D('p', 'muted', 'No directly retrieved source passages for this request.'));
  for (const item of list) {
    const article = D('article', 'source-result');
    const heading = D('div', 'source-heading');
    heading.append(D('strong', '', item.citation || item.id || 'OSHA provision'));
    let url = null;
    try {
      url = new URL(item.source_url);
      if (url.protocol !== 'https:' || url.hostname !== 'www.osha.gov') url = null;
    } catch { url = null; }
    if (url) {
      const link = D('a', '', 'View official text ↗');
      link.href = url.href; link.target = '_blank'; link.rel = 'noopener noreferrer';
      heading.append(link);
    }
    article.append(heading, D('p', '', (item.text || item.summary || '').slice(0, 900)));
    root.append(article);
  }
}
async function refreshDetails() {
  if (!state.scenario) return;
  const sid = encodeURIComponent(state.scenario.scenario_id);
  const branch = encodeURIComponent(state.branch);
  try {
    const [graph, history] = await Promise.all([
      api('/api/crs/assistant/' + sid + '/graph?branch=' + branch),
      api('/api/crs/scenarios/' + sid + '/history?branch=' + branch)
    ]);
    const graphRoot = $('#graph');
    graphRoot.replaceChildren();
    const defined = graph.deterministic_edges || [];
    const suggested = graph.proposed_edges || [];
    const rollup = {};
    for (const edge of defined) (rollup[edge.decision_id] ||= []).push(edge.condition_key);
    for (const [name, conditions] of Object.entries(rollup)) {
      graphRoot.append(D('div', 'graph-edge', name.replaceAll('_', ' ') + ' ← ' + conditions.join(', ')));
    }
    for (const edge of suggested) {
      graphRoot.append(D('div', 'graph-edge proposed', 'PROPOSED · ' + edge.decision_id + ' ← ' + edge.condition_key + ' (' + edge.review_status + ')'));
    }
    for (const candidate of (graph.candidate_decisions || [])) {
      const card = D('div', 'graph-edge proposed',
        'CANDIDATE · ' + candidate.decision_id + ': ' + candidate.status +
        ' · evaluated ' + candidate.evaluation_count + ' time(s) · ' + candidate.review_status);
      card.append(D('div', '', candidate.rationale));
      graphRoot.append(card);
    }
    const hist = $('#history');
    hist.replaceChildren();
    for (const event of (history.state_events || []).slice().reverse()) {
      const row = D('div', 'history-entry');
      row.append(D('strong', '', 'v' + event.version + ' · ' + event.op),
                 D('small', '', JSON.stringify(event.changes || event.changed || {}).slice(0, 250)));
      hist.append(row);
    }
    if (!hist.children.length) hist.append(D('p', 'muted', 'No state events.'));
  } catch (err) { alertError(err.message); }
}
$('#message').addEventListener('input', () => { $('#message-count').textContent = $('#message').value.length + ' / 2000'; });
$('#message-form').addEventListener('submit', async (event) => {
  event.preventDefault();
  if (state.loading) return;
  const text = $('#message').value.trim();
  if (!text) return;
  state.loading = true;
  $('#send').disabled = true;
  $('#send').textContent = 'Analyzing...';
  alertError('');
  try {
    const result = await api('/api/crs/assistant', 'POST', {
      text, scenario_id: state.scenario?.scenario_id || undefined,
      expected_version: state.scenario?.version, branch: state.branch
    });
    appendMessage('user', 'YOUR REPORT', text);
    appendMessage('assistant', result.mode === 'azure_openai' ? 'GROUNDED MODEL ANALYSIS' : 'RETRIEVAL / RULE-BASED ANALYSIS',
                  result.answer + (result.conflicts?.length ? '\nConflicting reports: ' + result.conflicts.join('; ') : ''),
                  result.status);
    if (result.scenario) {
      state.scenario = result.scenario;
      renderScenario(result.scenario);
      await refreshDetails();
    }
    renderEvidence(result.cited_osha);
    if (result.warnings?.length) $('#conversation-state').textContent = result.warnings[0];
    $('#message').value = '';
    $('#message-count').textContent = '0 / 2000';
  } catch (err) { alertError(err.message); }
  finally {
    state.loading = false;
    $('#send').disabled = false;
    $('#send').textContent = 'Analyze scenario';
  }
});
boot();
