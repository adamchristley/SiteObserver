'use strict';
const {randomUUID} = require('node:crypto');
function validatePrompt(input) {
  if(typeof input !== 'string') return 'Prompt must be a string.';
  if(!input.trim()) return 'Enter a non-empty prompt.';
  if(input.length > 2000) return 'Prompt exceeds the 2,000-character limit.';
  return null;
}
function makeDemoResponse(prompt) {
  return {
    status:'received',
    mode:'demo',
    response:'Your prompt was successfully received by an Azure Functions demonstration endpoint. No AI model is connected yet. This is a fixed acknowledgment rather than an AI-generated answer.',
    requestId:randomUUID(),
    promptLength:prompt.length,
    timestamp:new Date().toISOString()
  };
}
module.exports = {validatePrompt,makeDemoResponse};
