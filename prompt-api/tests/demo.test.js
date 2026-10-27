'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const {validatePrompt,makeDemoResponse} = require('../src/demo');
test('validate valid and invalid prompts',()=>{
  assert.equal(validatePrompt('hello Azure'),null);
  assert.match(validatePrompt(null),/string/);
  assert.match(validatePrompt('   '),/non-empty/);
  assert.match(validatePrompt('x'.repeat(2001)),/limit/);
});
test('demo response is not presented as AI',()=>{
  const result = makeDemoResponse('hello');
  assert.equal(result.mode,'demo');
  assert.equal(result.promptLength,5);
  assert.match(result.response,/No AI model/);
  assert.match(result.requestId,/^[0-9a-f-]{36}$/);
});
