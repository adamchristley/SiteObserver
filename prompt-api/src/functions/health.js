'use strict';
const {app} = require('@azure/functions');
app.http('health', {
  methods:['GET'],
  authLevel:'anonymous',
  handler:async () => ({
    status:200,
    jsonBody:{status:'ok',mode:'demo',service:'siteobserver-prompt-api'}
  })
});
