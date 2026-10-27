'use strict';
const $ = selector => document.querySelector(selector);
const promptField = $('#prompt');
const sendButton = $('#send');
function result(message, good) {
  $('#result').textContent = message;
  $('#result-status').textContent = good ? 'HTTP 200 · RECEIVED' : 'REQUEST FAILED';
  $('#result-status').className = good ? 'result-status ok' : 'result-status bad';
}
async function checkHealth() {
  $('#health').textContent = 'Checking connectivity...';
  $('#health-code').textContent = '...';
  try {
    const response = await fetch('/api/health', {cache:'no-store'});
    const payload = await response.json();
    if(!response.ok || payload.status !== 'ok') throw new Error('Unavailable');
    $('#health').textContent = 'Connected · Demo endpoint';
    $('#health-code').textContent = 'HTTP ' + response.status;
  } catch {
    $('#health').textContent = 'Offline · Check Azure deployment';
    $('#health-code').textContent = 'OFFLINE';
  }
}
promptField.addEventListener('input', () => $('#counter').textContent = promptField.value.length + ' / 2000');
document.querySelectorAll('[data-sample]').forEach(button => button.addEventListener('click', () => {
  promptField.value = button.dataset.sample;
  promptField.dispatchEvent(new Event('input'));
  promptField.focus();
}));
$('#retry').addEventListener('click', checkHealth);
$('#prompt-form').addEventListener('submit', async event => {
  event.preventDefault();
  const prompt = promptField.value.trim();
  if(!prompt) return promptField.focus();
  sendButton.disabled = true;
  sendButton.textContent = 'Sending...';
  $('#result-status').textContent = 'REQUEST IN PROGRESS';
  $('#result-status').className = 'result-status';
  const start = performance.now();
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), 30000);
  try {
    const response = await fetch('/api/prompt', {
      method:'POST',
      headers:{'Content-Type':'application/json'},
      body:JSON.stringify({prompt}),
      signal:controller.signal
    });
    const payload = await response.json();
    if(!response.ok) throw new Error(payload.error || 'HTTP '+response.status);
    if(typeof payload.response !== 'string') throw new Error('Invalid server response');
    result(payload.response, true);
    $('#mode').textContent = (payload.mode || 'demo').toUpperCase();
    $('#request-id').textContent = (payload.requestId || '--').slice(0, 12);
  } catch(error) {
    result(error.name === 'AbortError' ? 'The API timed out. Try again.' : 'Unable to reach the API: '+error.message, false);
    $('#request-id').textContent = '--';
  } finally {
    clearTimeout(timeout);
    $('#latency').textContent = Math.round(performance.now()-start)+' ms';
    sendButton.disabled = false;
    sendButton.textContent = 'Send to API ↗';
  }
});
checkHealth();
