"use strict";
const $ = id => document.getElementById(id);
const state = {csrf:null, sid:null, branch:"base", version:null, cases:[], branches:["base"]};
function elt(tag, cls, text){ const n=document.createElement(tag); if(cls)n.className=cls; if(text!==undefined)n.textContent=String(text); return n; }
function clear(node){node.replaceChildren();}
function flash(msg, bad=false){const n=$("flash");n.textContent=msg;n.className=bad?"error":"";n.hidden=false;setTimeout(()=>{n.hidden=true},6000);}
async function api(path,method="GET",data){
  const headers={"Accept":"application/json"};
  if(data!==undefined)headers["Content-Type"]="application/json";
  if(state.csrf&&method!=="GET")headers["X-CSRF-Token"]=state.csrf;
  const res=await fetch(path,{method,credentials:"same-origin",headers,body:data===undefined?undefined:JSON.stringify(data)});
  const json=await res.json().catch(()=>({error:"Invalid server response"}));
  if(!res.ok)throw Error(json.error||("HTTP "+res.status));
  return json;
}
function showWorkspace(){ $("login").hidden=true;$("workspace").hidden=false;$("signout").hidden=false;}
function showLogin(){ $("login").hidden=false;$("workspace").hidden=true;$("signout").hidden=true;}
function addText(parent, tag, text, cls){const n=elt(tag,cls,text);parent.append(n);return n;}
function link(parent, url, text){
  if(!url||!url.startsWith("https://www.osha.gov/"))return;
  const a=elt("a",null,text);a.href=url;a.target="_blank";a.rel="noopener noreferrer";parent.append(a);
}
function renderSources(sources){
  $("sourcesCount").textContent=String(sources.length);
  clear($("sourcesList"));
  if(!sources.length){addText($("sourcesList"),"li","No official documents indexed yet.");return;}
  for(const s of sources){const li=elt("li");link(li,s.source_url,s.section_id);addText(li,"span"," · "+s.chunks+" passages");$("sourcesList").append(li);}
}
async function status(){
  const s=await api("/api/workbench/status");state.cases=s.cases||[];
  renderSources(s.documents||[]);
  $("modelStatus").textContent=s.model_configured?"Configured":"Not configured";
  clear($("casePicker"));const opt=elt("option",null,"Select a saved case");opt.value="";$("casePicker").append(opt);
  const seen=new Set();
  for(const c of state.cases){if(seen.has(c.scenario_id))continue;seen.add(c.scenario_id);
    const o=elt("option",null,c.scenario_id.slice(0,12)+" · "+c.created_at.slice(0,10));o.value=c.scenario_id;$("casePicker").append(o);}
}
function renderDecision(container, d, model){
  const div=elt("div","decision");
  addText(div,"strong",d.decision_id.replaceAll("_"," "));
  addText(div,"span",d.stale?"STALE":d.status, "flag "+(d.stale?"stale":d.status));
  addText(div,"p",d.finding||d.rationale||"No rationale provided");
  if(model)addText(div,"small","LLM candidate: human review required.");
  if(d.depends_on?.length)addText(div,"div","Depends on: "+d.depends_on.join(", "),"dep");
  if(!model&&d.evidence_states?.length)addText(div,"div","Condition dependencies: "+d.evidence_states.map(x=>x.condition).join(", "),"dep");
  if(model&&d.citations?.length)addText(div,"div","Evidence chunk IDs: "+d.citations.join(", "),"dep");
  if(!model&&d.regulations?.length){for(const r of d.regulations){const block=elt("div","dep");link(block,r.source_url,r.id);div.append(block);}}
  addText(div,"small","Evaluations: "+(d.evaluation_count||1)+" · Last evaluated version: "+d.evaluated_version);
  container.append(div);
}
function render(data){
  state.sid=data.scenario_id;state.branch=data.branch;state.version=data.version;
  $("scenarioVersion").textContent="v"+data.version;
  $("scenarioBranch").textContent=data.branch;
  $("versionPill").textContent=data.branch+" · v"+data.version+" (CRS v"+data.core_version+")";
  $("send").disabled=false;
  $("conditions").textContent=JSON.stringify(data.conditions,null,2);
  $("extra").textContent=JSON.stringify(data.extra_facts,null,2);
  clear($("transcript"));
  for(const msg of data.messages||[]){const node=elt("div","message");addText(node,"small","Version "+msg.version+" · "+msg.created_at.slice(0,19).replace("T"," "));addText(node,"p",msg.text);$("transcript").append(node);}
  $("transcript").scrollTop=$("transcript").scrollHeight;
  clear($("ruleDecisions"));for(const d of data.rule_decisions||[])renderDecision($("ruleDecisions"),d,false);
  clear($("candidateDecisions"));for(const d of data.candidate_decisions||[])renderDecision($("candidateDecisions"),d,true);
  if(!(data.candidate_decisions||[]).length)addText($("candidateDecisions"),"div","No LLM assessments yet. Index OSHA documents and configure an approved model to enable this feature.","placeholder");
  $("changeNote").textContent=data.changed_keys?("Changed facts: "+(data.changed_keys.join(", ")||"No recognized changes")+" · Candidate reassessments: "+(data.reassessed_candidates||[]).length):"";
  renderSources(data.documents||[]);
  if(!state.branches.includes(data.branch))state.branches.push(data.branch);
  clear($("branchPicker"));
  for(const b of state.branches){const opt=elt("option",null,b);opt.value=b;$("branchPicker").append(opt);}
  $("branchPicker").value=data.branch;
}
async function go(fn){try{await fn()}catch(e){flash(e.message,true)}}
$("loginForm").addEventListener("submit",ev=>{ev.preventDefault();go(async()=>{
  const a=await api("/api/workbench/login","POST",{password:$("password").value});
  $("password").value="";state.csrf=a.csrf;showWorkspace();await status();flash("Research workspace ready");
})});
$("signout").onclick=()=>go(async()=>{await api("/api/workbench/logout","POST",{});state.csrf=null;state.sid=null;showLogin()});
$("create").onclick=()=>go(async()=>{const text=$("startText").value.trim();if(!text)throw Error("Enter a scenario first");
  const d=await api("/api/workbench/scenarios","POST",{text});state.branches=["base"];render(d);await status();flash("Scenario created");
});
$("casePicker").onchange=()=>go(async()=>{const sid=$("casePicker").value;if(!sid)return;
  state.branches=[...new Set(state.cases.filter(c=>c.scenario_id===sid).map(c=>c.branch).concat(["base"]))];
  render(await api("/api/workbench/scenarios/"+encodeURIComponent(sid)));
});
$("send").onclick=()=>go(async()=>{if(!state.sid)throw Error("Create or select a scenario");const text=$("followText").value.trim();if(!text)throw Error("Enter a question or correction");
  const d=await api("/api/workbench/scenarios/"+encodeURIComponent(state.sid)+"/messages","POST",{text,branch:state.branch,expected_version:state.version});
  render(d);$("followText").value="";flash("Turn stored and affected decisions updated");
});
$("branchPicker").onchange=()=>go(async()=>{if(!state.sid)return;
  render(await api("/api/workbench/scenarios/"+encodeURIComponent(state.sid)+"?branch="+encodeURIComponent($("branchPicker").value)));
});
$("fork").onclick=()=>go(async()=>{if(!state.sid)throw Error("Select a scenario first");
  const name=$("branchName").value.trim();if(!/^[A-Za-z0-9_-]{1,50}$/.test(name)||name==="base")throw Error("Enter a unique branch name");
  const d=await api("/api/workbench/scenarios/"+encodeURIComponent(state.sid)+"/branches","POST",{name,from_branch:state.branch});
  state.branches.push(name);render(d);$("branchName").value="";await status();flash("Hypothetical branch created");
});
$("ingest").onclick=()=>go(async()=>{const b=$("ingest");b.disabled=true;b.textContent="Downloading official OSHA documents...";
  try{const r=await api("/api/workbench/ingest","POST",{sections:["1926.650","1926.651","1926.652"]});await status();flash("Indexed "+r.ingested.reduce((n,x)=>n+x.chunks,0)+" passages");}
  finally{b.disabled=false;b.textContent="Download and index OSHA §§ 1926.650–652";}
});
$("search").onclick=()=>go(async()=>{const query=$("searchText").value.trim();if(!query)throw Error("Enter search terms");
  const d=await api("/api/workbench/search","POST",{query,limit:7});clear($("searchResults"));
  if(!d.ready)throw Error(d.warning);
  if(!d.matches.length)addText($("searchResults"),"p","No matches found");
  for(const x of d.matches){const node=elt("div","result");link(node,x.source_url,x.citation);addText(node,"p",x.text);addText(node,"small","Source SHA-256: "+x.source_sha256.slice(0,16)+" · Chunk "+x.chunk_id);$("searchResults").append(node);}
});
go(async()=>{try{const a=await api("/api/workbench/session");state.csrf=a.csrf;showWorkspace();await status()}catch(e){showLogin()}});
