'use strict';
const {app} = require('@azure/functions');
const {validatePrompt,makeDemoResponse} = require('../demo');
app.http('prompt', {
  methods:['POST'],
  authLevel:'anonymous',
  handler:async request => {
    let payload;
    try {payload = await request.json();}
    catch {return {status:400,jsonBody:{error:'Send a JSON object containing a prompt string.'}};}
    const error = validatePrompt(payload && payload.prompt);
    if(error) return {status:400,jsonBody:{error}};
    return {status:200,jsonBody:makeDemoResponse(payload.prompt.trim())};
  }
});
