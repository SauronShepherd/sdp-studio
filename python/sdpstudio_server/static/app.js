const persistedClientId = localStorage.getItem('svpClientId') || crypto.randomUUID();
localStorage.setItem('svpClientId', persistedClientId);
const state = {
  projects: [], projectId: null, project: null, pipeline: null, operators: [],
  selectedNodeId: null, selectedEdgeId: null, linkSource: null, problems: [],
  zoom: 1, panX: 0, panY: 0, undo: [], redo: [], saving: false,
  runtimeProfiles: [], runtimeProfileId: null,
  // Bearer credentials are memory-only; authentication is cookie-backed in
  // the server contract and must never be persisted in browser storage.
  clientId: persistedClientId, authToken: '',
  collabSocket: null, collabPing: null, dirty: false,
};
const $ = (id) => document.getElementById(id);
const esc = (s) => String(s ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#039;'}[c]));
const clone = (v) => JSON.parse(JSON.stringify(v));
const id26 = () => { const a='0123456789ABCDEFGHJKMNPQRSTVWXYZ'; return Array.from({length:26},()=>a[Math.floor(Math.random()*a.length)]).join(''); };

function base64Url(text){
  const bytes=new TextEncoder().encode(text);let binary='';for(const b of bytes)binary+=String.fromCharCode(b);
  return btoa(binary).replace(/\+/g,'-').replace(/\//g,'_').replace(/=+$/,'');
}
function wsProtocols(){const protocols=['sdpstudio.v1'];if(state.authToken)protocols.push(`sdpstudio.auth.${base64Url(state.authToken)}`);return protocols;}

async function api(path, opts={}) {
  const retried = Boolean(opts.__authRetried); const fetchOpts={...opts}; delete fetchOpts.__authRetried;
  const headers={'Content-Type':'application/json','X-SDPStudio-Client-ID':state.clientId,...(opts.headers||{})};
  if(state.authToken) headers.Authorization=`Bearer ${state.authToken}`;
  const res = await fetch(path, {...fetchOpts, headers});
  if(res.status===401 && !retried){
    const token=prompt('SDP Studio server access token');
    if(token){state.authToken=token;return api(path,{...opts,__authRetried:true});}
  }
  if (!res.ok) { let detail; try { detail=(await res.json()).detail; } catch { detail=await res.text(); } throw new Error(typeof detail==='string'?detail:JSON.stringify(detail)); }
  return res.status===204 ? null : res.json();
}
function setOutput(text) { $('outputView').textContent = typeof text==='string'?text:JSON.stringify(text,null,2); showBottom('output'); }
function setSaveState(text) { $('saveState').textContent=text; }
function currentNode() { return state.pipeline?.nodes.find(n=>n.id===state.selectedNodeId) || null; }
function opById(id) { return state.operators.find(o=>o.id===id); }
function pushUndo() { if (!state.pipeline) return; state.undo.push(clone(state.pipeline)); if (state.undo.length>80) state.undo.shift(); state.redo=[]; updateUndoButtons(); }
function updateUndoButtons() { $('undoBtn').disabled=!state.undo.length; $('redoBtn').disabled=!state.redo.length; }

async function bootstrap() {
  state.operators = await api('/api/operators');
  renderPalette();
  await refreshRuntimeProfiles();
  await refreshProjects();
  wireEvents();
  await refreshRuntime();
  if (state.projects.length) await openProject(state.projects[0].id); else $('newProjectDialog').showModal();
}
async function refreshRuntimeProfiles() {
  state.runtimeProfiles = await api('/api/runtime-profiles');
  if (!state.runtimeProfileId || !state.runtimeProfiles.some(p=>p.id===state.runtimeProfileId)) state.runtimeProfileId = state.runtimeProfiles[0]?.id || null;
  $('runtimeSelect').innerHTML = state.runtimeProfiles.map(p=>`<option value="${esc(p.id)}">${esc(p.name)} · ${esc(p.adapter)}</option>`).join('');
  if (state.runtimeProfileId) $('runtimeSelect').value = state.runtimeProfileId;
}
async function refreshRuntime() {
  if (!state.runtimeProfileId) return;
  try {
    const r = await api(`/api/runtime-profiles/${state.runtimeProfileId}/probe`);
    const profile = state.runtimeProfiles.find(p=>p.id===state.runtimeProfileId);
    $('runtimeBadge').textContent = r.available ? `${profile?.name||r.adapter} ready` : `${profile?.name||r.adapter} unavailable`;
    $('runtimeBadge').className = 'badge ' + (r.available?'ok':'warn');
    $('sparkState').textContent = r.available ? `Runtime: ${r.adapter}${r.spark_version?' · Spark '+r.spark_version:''}` : `Runtime: ${r.adapter} needs configuration/prerequisites`;
  } catch (e) {
    $('runtimeBadge').textContent='Runtime probe failed'; $('runtimeBadge').className='badge warn'; $('sparkState').textContent=e.message;
  }
}
function runtimeTemplate(adapter) {
  if(adapter==='spark-connect'||adapter==='databricks-connect') return {remote_env:'SPARK_REMOTE'};
  if(adapter==='kubernetes') return {master:'k8s://https://kubernetes.default.svc',image:'your-registry/spark:4.2.0',storage_uri:'s3a://your-bucket/sdpstudio/pipeline',namespace:'default',service_account:'spark'};
  return {};
}
async function refreshProjects() {
  state.projects = await api('/api/projects');
  $('projectSelect').innerHTML = state.projects.map(p=>`<option value="${esc(p.id)}">${esc(p.name)}</option>`).join('');
}
async function openProject(id) {
  if (!id) return;
  state.projectId=id; $('projectSelect').value=id;
  state.project=await api(`/api/projects/${id}`);
  state.pipeline=await api(`/api/projects/${id}/pipeline`);
  state.selectedNodeId=null; state.selectedEdgeId=null; state.undo=[]; state.redo=[]; state.dirty=false;
  connectCollaboration(id);
  renderAll();
  await Promise.all([refreshGit(), refreshRuns(), refreshHistory(), refreshCode(), refreshDebug()]);
  await validateModel(false);
}
function connectCollaboration(projectId){
  if(state.collabPing){clearInterval(state.collabPing);state.collabPing=null;}
  if(state.collabSocket){state.collabSocket.close();state.collabSocket=null;}
  const proto=location.protocol==='https:'?'wss':'ws';
  const ws=new WebSocket(`${proto}://${location.host}/ws/projects/${encodeURIComponent(projectId)}`,wsProtocols());
  state.collabSocket=ws;
  ws.onopen=()=>{if(state.collabSocket!==ws)return;$('collabState').textContent='Collaboration: connected';state.collabPing=setInterval(()=>{if(ws.readyState===WebSocket.OPEN)ws.send('ping');},25000);};
  ws.onmessage=async event=>{
    let msg;try{msg=JSON.parse(event.data);}catch{return;}
    if(msg.type==='presence'){$('collabState').textContent=`Editors connected: ${msg.count}`;return;}
    if(msg.type==='pipeline_saved'&&msg.client_id!==state.clientId&&state.pipeline&&msg.revision>state.pipeline.revision){
      if(state.dirty||state.saving){setSaveState(`Remote revision ${msg.revision} available · local edits preserved`);return;}
      try{state.pipeline=await api(`/api/projects/${projectId}/pipeline`);renderAll();await validateModel(false);setSaveState(`Updated to remote revision ${state.pipeline.revision}`);}catch(e){setOutput(e.message);}
    }
  };
  ws.onclose=()=>{if(state.collabSocket===ws)$('collabState').textContent='Collaboration: disconnected';};
}
function renderAll() { renderCanvas(); renderInspector(); updateUndoButtons(); $('emptyCanvas').style.display=state.pipeline?.nodes.length?'none':'block'; }

function renderPalette(filter='') {
  const groups={};
  for (const op of state.operators.filter(o=>o.title.toLowerCase().includes(filter.toLowerCase())||o.id.includes(filter.toLowerCase()))) (groups[op.category]??=[]).push(op);
  $('operatorPalette').innerHTML = Object.entries(groups).map(([cat,ops])=>`<div class="operator-group"><h4>${esc(cat)}</h4>${ops.map(op=>`<div class="operator-item" draggable="true" data-op="${esc(op.id)}"><span class="operator-icon">${esc(op.id.split('.')[0].slice(0,2).toUpperCase())}</span><span>${esc(op.title)}</span></div>`).join('')}</div>`).join('');
  document.querySelectorAll('.operator-item').forEach(el=>{
    el.addEventListener('dragstart', e=>e.dataTransfer.setData('application/x-sdpstudio-operator',el.dataset.op));
    el.addEventListener('dblclick', ()=>addNode(el.dataset.op, {x:140+Math.random()*120,y:120+Math.random()*120}));
  });
}
function defaultConfig(op) { const cfg={}; for (const f of op.fields||[]) if ('default' in f) cfg[f.name]=clone(f.default); return cfg; }
function addNode(type, pos) { if(!state.pipeline)return; const op=opById(type); pushUndo(); const node={id:id26(),type,operatorVersion:1,position:{x:Math.round(pos.x),y:Math.round(pos.y)},config:defaultConfig(op)}; state.pipeline.nodes.push(node); state.selectedNodeId=node.id; renderAll(); scheduleSave(); }
function deleteNode(id) { if(!state.pipeline)return; pushUndo(); state.pipeline.nodes=state.pipeline.nodes.filter(n=>n.id!==id); state.pipeline.edges=state.pipeline.edges.filter(e=>e.from.node!==id&&e.to.node!==id); if(state.selectedNodeId===id)state.selectedNodeId=null; renderAll(); scheduleSave(); }
function deleteEdge(id) { pushUndo(); state.pipeline.edges=state.pipeline.edges.filter(e=>e.id!==id); state.selectedEdgeId=null; renderCanvas(); scheduleSave(); }
function connectNodes(source, target) { if(!state.pipeline)return; if(source.node===target.node){state.linkSource=null;renderCanvas();return;} const exists=state.pipeline.edges.some(e=>e.to.node===target.node&&e.to.port===target.port); if(exists){setOutput(`Input ${target.port} is already connected.`);state.linkSource=null;renderCanvas();return;} pushUndo(); state.pipeline.edges.push({id:id26(),from:source,to:target}); state.linkSource=null; renderCanvas(); scheduleSave(); }

function renderCanvas() {
  if(!state.pipeline)return;
  const nodeLayer=$('nodeLayer'); nodeLayer.innerHTML='';
  for(const node of state.pipeline.nodes){
    const op=opById(node.type)||{title:node.type,inputs:[],outputs:[]};
    const el=document.createElement('div');
    const severity=state.problems.filter(p=>p.node_id===node.id).sort((a,b)=>a.severity==='error'?-1:1)[0]?.severity;
    el.className=`node ${state.selectedNodeId===node.id?'selected':''} ${severity||''}`;
    el.dataset.node=node.id; el.style.left=`${node.position.x}px`; el.style.top=`${node.position.y}px`;
    const summary = node.config.name || node.config.table || node.config.path || node.config.expression || op.category || '';
    el.innerHTML=`<div class="node-head"><span class="mini">${esc(node.type.split('.')[0].slice(0,3).toUpperCase())}</span><span>${esc(op.title)}</span></div><div class="node-body" title="${esc(summary)}">${esc(summary)}</div>`;
    (op.inputs||[]).forEach((port,i)=>{ const p=document.createElement('button'); p.className='port input'; p.title=`Input: ${port}`; p.style.top=`${42+i*20}px`; p.dataset.port=port; p.addEventListener('click',e=>{e.stopPropagation(); if(state.linkSource)connectNodes(state.linkSource,{node:node.id,port});}); el.appendChild(p); const label=document.createElement('span');label.className='port-label';label.style.top=`${40+i*20}px`;label.textContent=port;el.appendChild(label); });
    (op.outputs||[]).forEach((port,i)=>{ const p=document.createElement('button'); p.className=`port output ${state.linkSource?.node===node.id?'pending':''}`; p.title=`Output: ${port}`; p.style.top=`${44+i*20}px`; p.addEventListener('click',e=>{e.stopPropagation();state.linkSource={node:node.id,port};renderCanvas();});el.appendChild(p); });
    el.addEventListener('click',()=>{state.selectedNodeId=node.id;state.selectedEdgeId=null;renderAll();refreshDebug();});
    wireNodeDrag(el,node);
    nodeLayer.appendChild(el);
  }
  drawEdges();
  $('selectionState').textContent = state.selectedNodeId ? `Node ${state.selectedNodeId.slice(-6)}` : state.selectedEdgeId ? `Edge ${state.selectedEdgeId.slice(-6)}` : 'No selection';
}
function wireNodeDrag(el,node){
  const head=el.querySelector('.node-head'); let dragging=false,sx=0,sy=0,ox=0,oy=0,moved=false;
  head.addEventListener('pointerdown',e=>{dragging=true;moved=false;sx=e.clientX;sy=e.clientY;ox=node.position.x;oy=node.position.y;head.setPointerCapture(e.pointerId);});
  head.addEventListener('pointermove',e=>{if(!dragging)return;const dx=(e.clientX-sx)/state.zoom,dy=(e.clientY-sy)/state.zoom;if(Math.abs(dx)+Math.abs(dy)>3&&!moved){pushUndo();moved=true;}node.position.x=Math.round(ox+dx);node.position.y=Math.round(oy+dy);el.style.left=node.position.x+'px';el.style.top=node.position.y+'px';drawEdges();});
  head.addEventListener('pointerup',()=>{if(dragging&&moved)scheduleSave();dragging=false;});
}
function nodePortPoint(node,port,isOutput){ const op=opById(node.type)||{inputs:[],outputs:[]}; const ports=isOutput?op.outputs:op.inputs; const idx=Math.max(0,ports.indexOf(port)); return {x:node.position.x+(isOutput?196:0),y:node.position.y+50+idx*20}; }
function drawEdges(){
  const svg=$('edgeLayer'); svg.innerHTML=''; if(!state.pipeline)return;
  for(const edge of state.pipeline.edges){ const a=state.pipeline.nodes.find(n=>n.id===edge.from.node),b=state.pipeline.nodes.find(n=>n.id===edge.to.node); if(!a||!b)continue; const p1=nodePortPoint(a,edge.from.port,true),p2=nodePortPoint(b,edge.to.port,false);const dx=Math.max(50,Math.abs(p2.x-p1.x)*.45);const path=document.createElementNS('http://www.w3.org/2000/svg','path');path.setAttribute('d',`M ${p1.x} ${p1.y} C ${p1.x+dx} ${p1.y}, ${p2.x-dx} ${p2.y}, ${p2.x} ${p2.y}`);path.setAttribute('class',`edge-path ${state.selectedEdgeId===edge.id?'selected':''}`);path.addEventListener('click',e=>{e.stopPropagation();state.selectedEdgeId=edge.id;state.selectedNodeId=null;renderCanvas();renderInspector();});svg.appendChild(path); }
}

function renderInspector(){
  const box=$('inspectorContent');
  if(state.selectedEdgeId){box.innerHTML=`<div class="muted-text">Selected connection</div><div class="node-id">${esc(state.selectedEdgeId)}</div><button id="deleteEdgeBtn" class="danger-btn">Delete connection</button>`;$('deleteEdgeBtn').onclick=()=>deleteEdge(state.selectedEdgeId);return;}
  const node=currentNode(); if(!node){box.innerHTML='<div class="muted-text">Select a node to configure it.</div>';return;} const op=opById(node.type)||{fields:[],title:node.type};
  box.innerHTML=`<h3>${esc(op.title)}</h3><div class="node-id">${esc(node.id)} · ${esc(node.type)}</div><div class="panel-actions"><button id="previewNodeBtn" class="primary">Preview data</button></div><div id="fieldList"></div><button id="deleteNodeBtn" class="danger-btn">Delete node</button>`;
  const fields=$('fieldList');
  for(const f of op.fields||[]){ const label=document.createElement('label');label.textContent=f.label;let input;
    if(f.type==='boolean'){input=document.createElement('input');input.type='checkbox';input.checked=!!node.config[f.name];}
    else if(f.type==='enum'){input=document.createElement('select');for(const opt of f.options||[]){const o=document.createElement('option');o.value=opt;o.textContent=opt;o.selected=node.config[f.name]===opt;input.appendChild(o);}}
    else if(f.type==='json'||f.type==='code'){input=document.createElement('textarea');input.value=f.type==='json'?JSON.stringify(node.config[f.name]??f.default??{},null,2):(node.config[f.name]??'');}
    else {input=document.createElement('input');input.value=Array.isArray(node.config[f.name])?node.config[f.name].join(', '):(node.config[f.name]??'');input.placeholder=f.placeholder||'';}
    input.addEventListener('change',()=>{pushUndo();try{if(f.type==='boolean')node.config[f.name]=input.checked;else if(f.type==='json')node.config[f.name]=JSON.parse(input.value||'{}');else if(f.type==='list')node.config[f.name]=input.value.split(',').map(x=>x.trim()).filter(Boolean);else node.config[f.name]=input.value;setSaveState('Modified');renderCanvas();scheduleSave();}catch(err){setOutput(`Invalid ${f.label}: ${err.message}`);}}); label.appendChild(input);fields.appendChild(label);
  }
  $('previewNodeBtn').onclick=()=>previewNode(node.id);
  $('deleteNodeBtn').onclick=()=>deleteNode(node.id);
}

let saveTimer=null;
function scheduleSave(){ clearTimeout(saveTimer); state.dirty=true; setSaveState('Modified'); saveTimer=setTimeout(savePipeline,450); }
async function savePipeline(){ if(!state.pipeline||!state.projectId)return false;if(state.saving)return false;if(!state.dirty)return true; state.saving=true;setSaveState('Saving…');try{state.pipeline=await api(`/api/projects/${state.projectId}/pipeline`,{method:'PUT',body:JSON.stringify(state.pipeline)});state.dirty=false;setSaveState(`Saved · revision ${state.pipeline.revision}`);await refreshGit();return true;}catch(e){setSaveState(e.message.includes('current_revision')?'Revision conflict · local edits preserved':'Save failed');setOutput(e.message);return false;}finally{state.saving=false;} }

async function validateModel(show=true){ if(!state.projectId)return; try{const r=await api(`/api/projects/${state.projectId}/validate`,{method:'POST'});state.problems=r.problems||[];renderProblems();renderCanvas();if(show)setOutput(r.valid?'Validation passed.':`Validation found ${state.problems.length} problem(s).`);return r.valid;}catch(e){setOutput(e.message);return false;} }
function renderProblems(){ $('problemCount').textContent=state.problems.length; $('problemsView').innerHTML=state.problems.length?state.problems.map(p=>`<div class="problem-row ${esc(p.severity)}" data-node="${esc(p.node_id||'')}"><span class="sev">${esc(p.severity.toUpperCase())}</span><span>${esc(p.code)}</span><span>${esc(p.message)}</span></div>`).join(''):'<div class="muted-text">No problems.</div>'; document.querySelectorAll('.problem-row').forEach(r=>r.onclick=()=>{if(r.dataset.node){state.selectedNodeId=r.dataset.node;switchTab('canvas');renderAll();}}); }
async function generate(){ if(!state.projectId)return; setSaveState('Generating…');await savePipeline();try{const r=await api(`/api/projects/${state.projectId}/generate`,{method:'POST'});state.problems=r.problems||[];renderProblems();await refreshCode();setOutput(r.files?.length?`Generated ${r.files.map(f=>f.path).join(', ')}`:'Generation blocked by validation errors.');setSaveState('Generated');}catch(e){setOutput(e.message);setSaveState('Generate failed');} }
async function refreshCode(){ if(!state.projectId)return;try{const r=await api(`/api/projects/${state.projectId}/code`);$('codeView').textContent=r.content||'# Generate the pipeline to see code here.';}catch(e){$('codeView').textContent=e.message;} }
async function previewNode(nodeId){
  if(!state.projectId)return; showBottom('preview'); $('previewView').innerHTML='<div class="muted-text">Running bounded Spark preview…</div>';
  const saved=await savePipeline(); if(saved===false)return;
  try{const r=await api(`/api/projects/${state.projectId}/preview`,{method:'POST',body:JSON.stringify({node_id:nodeId,limit:50,runtime_profile_id:state.runtimeProfileId})});renderPreview(r);}catch(e){$('previewView').innerHTML=`<div class="muted-text">${esc(e.message)}</div>`;}
}
function renderPreview(r){
  if(!r.ok){const probs=(r.problems||[]).map(p=>`<div class="problem-row ${esc(p.severity||'error')}"><span class="sev">${esc((p.severity||'error').toUpperCase())}</span><span>${esc(p.code||'PREVIEW')}</span><span>${esc(p.message||'Preview failed')}</span></div>`).join('');$('previewView').innerHTML=probs||`<pre>${esc(r.output||'Preview failed')}</pre>`;return;}
  const rows=r.rows||[];const cols=rows.length?Array.from(new Set(rows.flatMap(x=>Object.keys(x)))):[];
  const fields=r.schema?.fields||[];
  const schema=`<details><summary>Schema · ${fields.length} fields</summary><div class="schema-chips">${fields.map(f=>`<span>${esc(f.name)} <small>${esc(typeof f.type==='string'?f.type:JSON.stringify(f.type))}${f.nullable?'?':''}</small></span>`).join('')}</div></details>`;
  const table=cols.length?`<div class="preview-table-wrap"><table class="preview-table"><thead><tr>${cols.map(c=>`<th>${esc(c)}</th>`).join('')}</tr></thead><tbody>${rows.map(row=>`<tr>${cols.map(c=>`<td title="${esc(row[c] == null?'null':typeof row[c]==='object'?JSON.stringify(row[c]):row[c])}">${esc(row[c] == null?'null':typeof row[c]==='object'?JSON.stringify(row[c]):row[c])}</td>`).join('')}</tr>`).join('')}</tbody></table></div>`:'<div class="muted-text">Preview returned no rows.</div>';
  $('previewView').innerHTML=`<div class="preview-meta">${rows.length} row(s) · ${esc(r.runtime_adapter||'spark')} · bounded to ${esc(r.limit||50)}</div>${schema}${table}`;
}
async function dryRun(){ await generate();try{const r=await api(`/api/projects/${state.projectId}/dry-run`,{method:'POST',body:JSON.stringify({runtime_profile_id:state.runtimeProfileId})});setOutput(r.output||r.problems||r);}catch(e){setOutput(e.message);} }
async function runPipeline(){ await generate();try{const r=await api(`/api/projects/${state.projectId}/runs`,{method:'POST',body:JSON.stringify({mode:'incremental',selected:[],runtime_profile_id:state.runtimeProfileId})});setOutput(`Run ${r.id}\nStatus: ${r.status}${r.error?'\n'+r.error:''}`);await refreshRuns();}catch(e){setOutput(e.message);} }

async function refreshGit(){
  if(!state.projectId)return;
  try{
    const [s, remotes] = await Promise.all([
      api(`/api/projects/${state.projectId}/git/status`),
      api(`/api/projects/${state.projectId}/git/remotes`)
    ]);
    $('branchBadge').textContent=s.initialized?(s.branch+(s.dirty?' *':'')):'no git';
    $('branchBadge').className='badge '+(s.dirty?'warn':'muted');
    const origin=remotes.origin||'';
    let html=`
      <div class="panel-actions"><button id="gitInit">Init</button><button id="gitDiff">Diff</button><button id="gitCommit">Commit</button></div>
      <div class="panel-list-item"><strong>${esc(s.branch||'No repository')}</strong><small>${s.dirty?'Working tree has changes':'Working tree clean'}</small></div>
      <label style="display:block;margin-top:10px;color:var(--muted);font-size:11px">Origin remote<input id="gitRemoteUrl" style="display:block;width:100%;margin-top:5px" placeholder="git@github.com:org/repo.git" value="${esc(origin)}" /></label>
      <div class="panel-actions"><button id="gitSaveRemote">Set origin</button><button id="gitFetch">Fetch</button><button id="gitPull">Pull FF</button><button id="gitPush">Push</button></div>
      <div class="panel-actions"><button id="gitReview">Open PR / MR</button></div>`;
    if(s.entries?.length)html+=s.entries.map(x=>`<div class="panel-list-item"><small>${esc(x)}</small></div>`).join('');
    $('gitPanel').innerHTML=html;
    $('gitInit').onclick=async()=>{await api(`/api/projects/${state.projectId}/git/init`,{method:'POST'});refreshGit();};
    $('gitDiff').onclick=async()=>setOutput((await api(`/api/projects/${state.projectId}/git/diff`)).diff||'No diff.');
    $('gitCommit').onclick=async()=>{const m=prompt('Commit message','Update visual pipeline');if(m){try{setOutput(await api(`/api/projects/${state.projectId}/git/commit`,{method:'POST',body:JSON.stringify({message:m})}));refreshGit();}catch(e){setOutput(e.message);}}};
    $('gitSaveRemote').onclick=async()=>{try{const url=$('gitRemoteUrl').value.trim();setOutput(await api(`/api/projects/${state.projectId}/git/remotes`,{method:'POST',body:JSON.stringify({name:'origin',url})}));refreshGit();}catch(e){setOutput(e.message);}};
    $('gitFetch').onclick=async()=>{try{setOutput(await api(`/api/projects/${state.projectId}/git/fetch`,{method:'POST',body:JSON.stringify({remote:'origin'})}));refreshGit();}catch(e){setOutput(e.message);}};
    $('gitPull').onclick=async()=>{try{setOutput(await api(`/api/projects/${state.projectId}/git/pull`,{method:'POST',body:JSON.stringify({remote:'origin',branch:null})}));refreshGit();}catch(e){setOutput(e.message);}};
    $('gitPush').onclick=async()=>{try{setOutput(await api(`/api/projects/${state.projectId}/git/push`,{method:'POST',body:JSON.stringify({remote:'origin',branch:null})}));refreshGit();}catch(e){setOutput(e.message);}};
    $('gitReview').onclick=async()=>{
      const head=(s.branch||'').split('...')[0].trim();
      if(!origin){setOutput('Set an origin remote first.');return;}
      const title=prompt('Pull / merge request title','Update visual pipeline'); if(!title)return;
      const base=prompt('Target branch','main')||'main';
      try{const r=await api(`/api/projects/${state.projectId}/git/review`,{method:'POST',body:JSON.stringify({provider:'auto',remote:'origin',title,body:'Created from SDP Studio',head,base})});setOutput(r);}catch(e){setOutput(e.message+'\nStore provider credentials in the SDP Studio secrets vault as provider.github.token or provider.gitlab.token.');}
    };
  }catch(e){$('gitPanel').innerHTML=`<div class="muted-text">${esc(e.message)}</div>`;}
}
async function refreshRuns(){
  if(!state.projectId)return;
  try{
    const runs=await api(`/api/projects/${state.projectId}/runs`);
    $('runsPanel').innerHTML=runs.length?runs.map(r=>`<div class="panel-list-item run-item" data-run="${esc(r.id)}"><strong>${esc(r.status)} · ${esc(r.mode)}</strong><small>${esc(r.created_at)} · ${esc(r.id.slice(-8))}</small><div class="panel-actions"><button data-open-run="${esc(r.id)}">Details</button><button data-bundle="${esc(r.id)}">Debug bundle</button></div></div>`).join(''):'<div class="muted-text">No runs yet.</div>';
    document.querySelectorAll('[data-open-run]').forEach(el=>el.onclick=async e=>{e.stopPropagation();const r=await api(`/api/runs/${el.dataset.openRun}`);setOutput(r);});
    document.querySelectorAll('[data-bundle]').forEach(el=>el.onclick=e=>{e.stopPropagation();window.open(`/api/runs/${el.dataset.bundle}/debug-bundle`,'_blank');});
    renderRunCompare(runs);
  }catch(e){$('runsPanel').innerHTML=esc(e.message);}
}
async function refreshHistory(){
  if(!state.projectId)return;
  try{
    const h=await api(`/api/projects/${state.projectId}/history`);
    $('historyPanel').innerHTML=h.length?h.map(x=>`<div class="panel-list-item"><strong>Revision ${esc(x.revision)}</strong><small>${esc(x.reason)} · ${esc(x.created_at)}</small><div class="panel-actions"><button data-diff-history="${esc(x.id)}">Diff</button><button data-restore="${esc(x.id)}">Restore</button></div></div>`).join(''):'<div class="muted-text">No local snapshots yet.</div>';
    document.querySelectorAll('[data-diff-history]').forEach(b=>b.onclick=async()=>{try{setOutput(await api(`/api/projects/${state.projectId}/history/${b.dataset.diffHistory}/diff`));}catch(e){setOutput(e.message);}});
    document.querySelectorAll('[data-restore]').forEach(b=>b.onclick=async()=>{if(confirm('Restore this local snapshot?')){state.pipeline=await api(`/api/projects/${state.projectId}/history/${b.dataset.restore}/restore`,{method:'POST'});renderAll();refreshHistory();}});
  }catch(e){$('historyPanel').innerHTML=esc(e.message);}
}
async function refreshDebug(){
  if(!state.projectId)return;
  try{
    const p=await api(`/api/projects/${state.projectId}/debug/plan`);
    $('debugPlan').innerHTML=p.nodes.map(n=>`<div class="debug-row"><span>${n.ordinal}</span><span>${esc(n.type)}</span><span class="risk-${esc(n.risk)}">${esc(n.risk)}</span></div>`).join('')+(p.risks.length?`<p class="muted-text">${p.risks.length} performance diagnostic(s)</p>`:'');
    const node=currentNode();
    if(node){const t=await api(`/api/projects/${state.projectId}/debug/row-trace/${node.id}`);$('rowTrace').innerHTML=t.path.map((s,i)=>`<div class="panel-list-item"><strong>${i+1}. ${esc(s.type)}</strong><small>${esc(s.effect||'Pass-through/source/output')}</small></div>`).join('');}
    else $('rowTrace').innerHTML='<div class="muted-text">Select a node to trace its upstream transformation path.</div>';
    await refreshExecutionHealth();
  }catch(e){$('debugPlan').textContent=e.message;}
}
async function refreshExecutionHealth(){
  const host=$('executionHealth');if(!host)return;
  try{
    const runs=await api(`/api/projects/${state.projectId}/runs`);
    if(!runs.length){host.innerHTML='<div class="muted-text">No runs yet. Event-log analysis appears here after Spark execution.</div>';return;}
    let detail=null,analysis=null;
    for(const run of runs.slice(0,10)){
      const candidate=await api(`/api/runs/${run.id}`);
      const event=[...(candidate.events||[])].reverse().find(e=>e.kind==='debug'&&e.data?.stages);
      if(event){detail=candidate;analysis=event.data;break;}
    }
    if(!analysis){
      const latest=await api(`/api/runs/${runs[0].id}`);
      const mapped=(latest.events||[]).filter(e=>e.kind==='diagnostic');
      host.innerHTML=`<div class="muted-text">Latest runs have no Spark event-log stage data yet.${mapped.length?` ${mapped.length} generated-code failure(s) were mapped back to visual nodes.`:''}</div>`;
      return;
    }
    const stages=analysis.stages||[];const maxMs=Math.max(1,...stages.map(s=>Number(s.max_task_ms||0)));
    host.innerHTML=`<div class="health-summary"><strong>Run ${esc(detail.id.slice(-8))}</strong><span>${stages.length} stages</span><span>${stages.filter(s=>Number(s.skew_score)>=5).length} severe skew</span></div>`+stages.map(s=>{const width=Math.max(3,Math.round(Number(s.max_task_ms||0)/maxMs*100));const risk=Number(s.skew_score)>=5?'high':Number(s.skew_score)>=2?'medium':'low';return `<div class="health-stage"><div class="health-label"><span>Stage ${esc(s.stage_id)} · ${esc(s.name||'unnamed')}</span><span class="risk-${risk}">skew ${esc(s.skew_score)}</span></div><div class="health-track"><span style="width:${width}%"></span></div><small>${esc(s.task_count)} tasks · max ${esc(s.max_task_ms)} ms · shuffle read ${formatBytes(s.shuffle_read_bytes)} · write ${formatBytes(s.shuffle_write_bytes)}</small></div>`;}).join('');
  }catch(e){host.innerHTML=`<div class="muted-text">${esc(e.message)}</div>`;}
}
function formatBytes(value){const n=Number(value||0);if(n<1024)return `${n} B`;if(n<1024*1024)return `${(n/1024).toFixed(1)} KiB`;if(n<1024*1024*1024)return `${(n/1024/1024).toFixed(1)} MiB`;return `${(n/1024/1024/1024).toFixed(2)} GiB`;}
function renderRunCompare(runs){ if(!runs||runs.length<2){$('runCompare').innerHTML='<div class="muted-text">Run the pipeline at least twice to compare code hash, status, mode, and duration.</div>';return;} const a=runs[1],b=runs[0];$('runCompare').innerHTML=`<div class="panel-actions"><button id="compareLatest">Compare ${esc(a.id.slice(-6))} → ${esc(b.id.slice(-6))}</button></div><pre id="compareOutput" class="muted-text"></pre>`;$('compareLatest').onclick=async()=>{const r=await api(`/api/projects/${state.projectId}/debug/compare-runs`,{method:'POST',body:JSON.stringify({left_run_id:a.id,right_run_id:b.id})});$('compareOutput').textContent=JSON.stringify(r,null,2);}; }

function autoLayout(){ if(!state.pipeline)return;pushUndo();const indeg={},out={};for(const n of state.pipeline.nodes){indeg[n.id]=0;out[n.id]=[];}for(const e of state.pipeline.edges){if(indeg[e.to.node]!=null&&out[e.from.node]){indeg[e.to.node]++;out[e.from.node].push(e.to.node);}}const q=Object.keys(indeg).filter(id=>indeg[id]===0),layer={};q.forEach(id=>layer[id]=0);while(q.length){const id=q.shift();for(const c of out[id]){layer[c]=Math.max(layer[c]||0,(layer[id]||0)+1);if(--indeg[c]===0)q.push(c);}}const buckets={};for(const n of state.pipeline.nodes)(buckets[layer[n.id]||0]??=[]).push(n);for(const [l,nodes] of Object.entries(buckets))nodes.forEach((n,i)=>{n.position={x:70+Number(l)*260,y:70+i*130};});renderCanvas();scheduleSave(); }
function fitCanvas(){ if(!state.pipeline?.nodes.length)return;const xs=state.pipeline.nodes.map(n=>n.position.x),ys=state.pipeline.nodes.map(n=>n.position.y);const minX=Math.min(...xs),maxX=Math.max(...xs)+220,minY=Math.min(...ys),maxY=Math.max(...ys)+110;const vp=$('canvasViewport').getBoundingClientRect();state.zoom=Math.max(.45,Math.min(1.25,Math.min((vp.width-80)/(maxX-minX),(vp.height-80)/(maxY-minY))));state.panX=40-minX*state.zoom;state.panY=40-minY*state.zoom;applyTransform(); }
function applyTransform(){$('canvasWorld').style.transform=`translate(${state.panX}px,${state.panY}px) scale(${state.zoom})`;$('zoomLabel').textContent=Math.round(state.zoom*100)+'%';}
function switchTab(name){document.querySelectorAll('.tabs [data-tab]').forEach(b=>b.classList.toggle('active',b.dataset.tab===name));document.querySelectorAll('.tab-pane').forEach(p=>p.classList.remove('active'));$('tab'+name[0].toUpperCase()+name.slice(1)).classList.add('active');if(name==='code')refreshCode();if(name==='debug')refreshDebug();}
function showBottom(name){document.querySelectorAll('[data-bottom]').forEach(b=>b.classList.toggle('active',b.dataset.bottom===name));$('problemsView').classList.toggle('active',name==='problems');$('previewView').classList.toggle('active',name==='preview');$('outputView').classList.toggle('active',name==='output');}

function wireEvents(){
  $('projectSelect').onchange=e=>openProject(e.target.value); $('newProjectBtn').onclick=()=>$('newProjectDialog').showModal(); $('cloneProjectBtn').onclick=()=>$('cloneProjectDialog').showModal();
  $('runtimeSelect').onchange=async e=>{state.runtimeProfileId=e.target.value;await refreshRuntime();}; $('newRuntimeBtn').onclick=()=>$('newRuntimeDialog').showModal();
  $('newProjectForm').addEventListener('submit',async e=>{e.preventDefault();const name=$('newProjectName').value.trim();if(!name)return;try{const p=await api('/api/projects',{method:'POST',body:JSON.stringify({name,example:$('newProjectExample').checked?'retail-etl':null})});$('newProjectDialog').close();await refreshProjects();await openProject(p.id);}catch(err){setOutput(err.message);}});
  $('cloneProjectForm').addEventListener('submit',async e=>{e.preventDefault();const name=$('cloneProjectName').value.trim(),remote_url=$('cloneProjectRemote').value.trim(),branch=$('cloneProjectBranch').value.trim()||null;if(!name||!remote_url)return;try{setSaveState('Cloning repository…');const p=await api('/api/projects/clone',{method:'POST',body:JSON.stringify({name,remote_url,branch})});$('cloneProjectDialog').close();await refreshProjects();await openProject(p.id);setSaveState('Repository cloned');}catch(err){setSaveState('Clone failed');setOutput(err.message);}});
  $('newRuntimeAdapter').onchange=e=>{$('newRuntimeConfig').value=JSON.stringify(runtimeTemplate(e.target.value),null,2);};
  $('newRuntimeForm').addEventListener('submit',async e=>{e.preventDefault();try{const adapter=$('newRuntimeAdapter').value;const config=JSON.parse($('newRuntimeConfig').value||'{}');const p=await api('/api/runtime-profiles',{method:'POST',body:JSON.stringify({name:$('newRuntimeName').value.trim(),adapter,config})});$('newRuntimeDialog').close();await refreshRuntimeProfiles();state.runtimeProfileId=p.id;$('runtimeSelect').value=p.id;await refreshRuntime();}catch(err){setOutput(err.message);}});
  $('operatorSearch').oninput=e=>renderPalette(e.target.value);
  document.querySelectorAll('.rail button').forEach(b=>b.onclick=()=>{document.querySelectorAll('.rail button').forEach(x=>x.classList.remove('active'));b.classList.add('active');document.querySelectorAll('.activity').forEach(x=>x.classList.remove('active'));$('activity'+b.dataset.activity[0].toUpperCase()+b.dataset.activity.slice(1)).classList.add('active');if(b.dataset.activity==='git')refreshGit();if(b.dataset.activity==='runs')refreshRuns();if(b.dataset.activity==='history')refreshHistory();});
  document.querySelectorAll('.tabs [data-tab]').forEach(b=>b.onclick=()=>switchTab(b.dataset.tab)); document.querySelectorAll('[data-bottom]').forEach(b=>b.onclick=()=>showBottom(b.dataset.bottom));
  $('canvasViewport').addEventListener('dragover',e=>e.preventDefault()); $('canvasViewport').addEventListener('drop',e=>{e.preventDefault();const type=e.dataTransfer.getData('application/x-sdpstudio-operator');if(!type)return;const r=$('canvasViewport').getBoundingClientRect();addNode(type,{x:(e.clientX-r.left-state.panX)/state.zoom,y:(e.clientY-r.top-state.panY)/state.zoom});});
  $('canvasViewport').addEventListener('click',e=>{if(e.target===$('canvasViewport')||e.target===$('canvasWorld')||e.target===$('nodeLayer')){state.selectedNodeId=null;state.selectedEdgeId=null;state.linkSource=null;renderAll();}});
  $('validateBtn').onclick=()=>validateModel(true); $('generateBtn').onclick=generate; $('dryRunBtn').onclick=dryRun; $('runBtn').onclick=runPipeline;
  $('copyCodeBtn').onclick=async()=>{await navigator.clipboard.writeText($('codeView').textContent);setSaveState('Code copied');};
  $('undoBtn').onclick=()=>{if(!state.undo.length)return;const rev=state.pipeline.revision;state.redo.push(clone(state.pipeline));state.pipeline=state.undo.pop();state.pipeline.revision=rev;renderAll();scheduleSave();}; $('redoBtn').onclick=()=>{if(!state.redo.length)return;const rev=state.pipeline.revision;state.undo.push(clone(state.pipeline));state.pipeline=state.redo.pop();state.pipeline.revision=rev;renderAll();scheduleSave();};
  $('layoutBtn').onclick=autoLayout; $('fitBtn').onclick=fitCanvas; $('zoomIn').onclick=()=>{state.zoom=Math.min(1.8,state.zoom+.1);applyTransform();}; $('zoomOut').onclick=()=>{state.zoom=Math.max(.35,state.zoom-.1);applyTransform();};
  window.addEventListener('keydown',e=>{if((e.ctrlKey||e.metaKey)&&e.key==='z'){e.preventDefault();$('undoBtn').click();}if((e.ctrlKey||e.metaKey)&&e.key==='y'){e.preventDefault();$('redoBtn').click();}if(e.key==='Delete'||e.key==='Backspace'){const tag=document.activeElement?.tagName;if(['INPUT','TEXTAREA','SELECT'].includes(tag))return;if(state.selectedNodeId)deleteNode(state.selectedNodeId);else if(state.selectedEdgeId)deleteEdge(state.selectedEdgeId);}if((e.ctrlKey||e.metaKey)&&e.key==='c'&&currentNode()){window.__svpClipboard=clone(currentNode());}if((e.ctrlKey||e.metaKey)&&e.key==='v'&&window.__svpClipboard){e.preventDefault();pushUndo();const n=clone(window.__svpClipboard);n.id=id26();n.position.x+=30;n.position.y+=30;state.pipeline.nodes.push(n);state.selectedNodeId=n.id;renderAll();scheduleSave();}});
}
bootstrap().catch(e=>setOutput(e.stack||e.message));
