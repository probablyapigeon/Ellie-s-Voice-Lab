'use strict';
const $ = selector => document.querySelector(selector);
const esc = value => String(value ?? '').replace(/[&<>"']/g, char => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[char]));
let currentStudy = null, simulation = null, displayOrder = [], dataFolder = '';
let messageTimer;
function message(text) { $('#message').textContent = text; $('#message').hidden = false; clearTimeout(messageTimer); messageTimer = setTimeout(() => $('#message').hidden = true, 9000); }
async function api(path, data) {
  const response = await fetch(path, data === undefined ? {} : {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify(data)});
  const result = await response.json();
  if (!response.ok) throw new Error(result.error || 'The request could not be completed.');
  return result;
}
async function safely(action, button) {
  if (button?.disabled) return;
  if (button) button.disabled = true;
  try { await action(); } catch(error) { message(error.message); } finally { if (button) button.disabled = false; }
}
function navigate(view) {
  document.querySelectorAll('.view').forEach(node => node.hidden = node.id !== `view-${view}`);
  document.querySelectorAll('.nav').forEach(node => node.classList.toggle('active', node.dataset.view === view));
  $('#breadcrumb').textContent = `RESEARCH / ${view.toUpperCase()}`;
  if (view === 'studies') safely(loadStudies);
  window.scrollTo({top:0, behavior:'instant'});
}
function newStudy() { $('#create-dialog').showModal(); $('#study-form input[name=title]').focus(); }
async function loadStudies() {
  const result = await api('/api/studies'); dataFolder = result.data_directory;
  $('#data-location').textContent = `Local records folder: ${dataFolder}. Back it up separately; the database is not part of the program download.`;
  $('#version').textContent = `Version ${result.version}`;
  $('#study-list').innerHTML = result.studies.length ? result.studies.map(s => `<div class="study-card"><div><h2>${esc(s.title)}</h2><p>${esc(s.subject)} · ${s.trials} trials · ${esc(s.status)} <span class="badge ${s.synthetic ? 'synthetic' : ''}">${s.synthetic ? 'SYNTHETIC EXAMPLE' : 'OBSERVATION'}</span></p></div><button class="secondary open-study" data-id="${esc(s.id)}">Open notebook ↗</button></div>`).join('') : `<div class="empty"><h2>The first page is yours.</h2><p>Start a study, or explore the synthetic example to see the workflow.</p><button class="primary" id="empty-new">Create a study</button></div>`;
  if (!currentStudy) { $('#study-detail').hidden = true; $('#study-list').hidden = false; }
}
async function openStudy(id) {
  currentStudy = await api(`/api/studies/${id}`);
  renderStudy();
}
function renderStudy() {
  const s = currentStudy, report = s.summary;
  $('#study-list').hidden = true; $('#study-detail').hidden = false;
  const pending = s.trials.find(t => t.status === 'pending');
  const corroboration = report.corroboration_assessed ? `${Math.round(report.corroboration_rate * 100)}%` : '—';
  $('#study-detail').innerHTML = `<button class="back" id="back-studies">← All studies</button>
    <div class="study-heading"><div><span class="badge ${s.synthetic ? 'synthetic' : ''}">${s.synthetic ? 'SYNTHETIC EXAMPLE · NOT BIRD DATA' : 'OBSERVATION STUDY'}</span><h2>${esc(s.title)}</h2><p class="small">${esc(s.subject)} · ${esc(s.status)} · protocol locked ${new Date(s.created_at).toLocaleDateString()}</p></div><div class="actions"><a class="secondary" href="/api/studies/${s.id}/export">Export JSON</a><a class="secondary" href="/api/studies/${s.id}/csv">CSV</a><a class="secondary" href="/api/studies/${s.id}/receipt">Receipt</a></div></div>
    <div class="panel"><h3>Your question</h3><p>${esc(s.question)}</p><div class="small"><strong>Corroboration criterion:</strong> ${esc(s.criterion)}</div><p class="small">Limit: ${s.max_trials} trials. Exports include all notes and unblinded controls; review before sharing.</p></div>
    <div class="metrics"><div class="metric"><strong>${report.responses}</strong><span>Recorded selections</span></div><div class="metric"><strong>${corroboration}</strong><span>Corroborated / ${report.corroboration_assessed} assessed</span></div><div class="metric"><strong>${report.missing}</strong><span>No response · retained separately</span></div><div class="metric"><strong>${report.withdrawals + report.distress}</strong><span>Withdrawal or distress</span></div></div>
    ${s.status === 'open' ? pending ? observationForm(pending) : trialForm(s) : `<div class="selection-note">This session is closed: ${esc(s.closed_reason)}. Records remain available for review and export.</div>`}
    ${analysis(s)}
    <div class="panel"><h2>The observation timeline</h2>${s.trials.length ? `<div class="table-wrap"><table><thead><tr><th>Trial</th><th>Context</th><th>Selection / outcome</th><th>Corroboration</th></tr></thead><tbody>${s.trials.map(t => `<tr><td>${t.number}</td><td>${esc(t.context || '—')}</td><td>${esc(t.observation?.choice || t.observation?.outcome || 'Awaiting observation')}</td><td>${esc(t.observation?.corroboration || '—')}</td></tr>`).join('')}</tbody></table></div>${s.trials.filter(t => t.observation).map(t => `<details><summary>Trial ${t.number} · notes and committed comparison trace</summary><p class="small">${esc(t.observation.notes || 'No notes recorded.')}</p><pre class="trace">${esc(JSON.stringify({display_order:t.display_order,features:t.features,prompt:t.prompt,target:t.target,predictions:t.predictions,observation:t.observation}, null, 2))}</pre></details>`).join('')}` : '<p class="small">Your committed trials and observations will appear here.</p>'}</div>
    ${s.status === 'open' && !pending ? '<button class="secondary" id="close-study">Close session & review controls</button>' : ''}`;
  if (!pending && s.status === 'open') {
    displayOrder = [...s.choices]; renderFeatureRows();
    $('#trial-form').addEventListener('submit', commitTrial);
  }
  if (pending) { $('#observation-form').addEventListener('submit', recordObservation); $('#observation-outcome').addEventListener('change', outcomeChanged); }
}
function trialForm(s) {
  return `<form id="trial-form" class="panel"><div class="trial-steps"><span class="current">1 · Before the response</span><span>2 · Record observation</span><span>3 · Review</span></div><h2>Commit trial ${s.trials.length + 1}.</h2><p class="small">Record the setup as it exists on the bird’s speech board. Comparisons lock before the response.</p>
    <div class="two-cols"><label>Exact prompt · optional<input name="prompt" maxlength="2000" placeholder="Leave blank for an unprompted interaction"></label><label>Context · observable details<input name="context" maxlength="2000" placeholder="Time, available items, recent activity"></label></div>
    <label>Objective answer · only for a predefined discrimination task<select name="target"><option value="">No objective answer / free choice</option>${s.choices.map(c => `<option>${esc(c)}</option>`).join('')}</select></label>
    <p class="small">Record display order with ↑ and ↓. Brightness: 0–1; context weight: 0–10. Defaults are neutral. Ratings need a consistent method declared in your research protocol.</p><div id="feature-rows" class="feature-rows"></div>
    <div class="actions"><button type="submit" class="primary">Lock trial & comparisons ↗</button></div></form>`;
}
function renderFeatureRows(saved={}) {
  $('#feature-rows').innerHTML = displayOrder.map((c,i) => `<div class="feature-row" data-choice="${esc(c)}"><strong>${i + 1}. ${esc(c)}</strong><label>Brightness<input class="brightness" type="number" min="0" max="1" step="0.05" value="${saved[c]?.brightness ?? 0.5}" required></label><label>Context weight<input class="context-weight" type="number" min="0" max="10" step="0.1" value="${saved[c]?.context_weight ?? 1}" required></label><div class="reorder"><button type="button" data-move="-1" data-index="${i}" aria-label="Move ${esc(c)} up" ${i === 0 ? 'disabled' : ''}>↑</button><button type="button" data-move="1" data-index="${i}" aria-label="Move ${esc(c)} down" ${i === displayOrder.length-1 ? 'disabled' : ''}>↓</button></div></div>`).join('');
}
function readFeatures() { return [...document.querySelectorAll('.feature-row')].map(row => ({choice:row.dataset.choice, brightness:Number(row.querySelector('.brightness').value), context_weight:Number(row.querySelector('.context-weight').value)})); }
async function commitTrial(event) {
  event.preventDefault(); const form = event.target, data = new FormData(form), button = form.querySelector('button[type=submit]');
  await safely(async () => { await api(`/api/studies/${currentStudy.id}/trials`, {prompt:data.get('prompt'),context:data.get('context'),target:data.get('target') || null,features:readFeatures()}); await openStudy(currentStudy.id); message('Trial committed. Record what happened next.'); }, button);
}
function observationForm(t) {
  return `<form id="observation-form" class="panel"><div class="trial-steps"><span>1 · Trial committed</span><span class="current">2 · Record observation</span><span>3 · Review</span></div><h2 class="observation-head">What happened in trial ${t.number}?</h2><p class="small">Display: ${esc(t.display_order.join(' → '))} · Prompt: ${esc(t.prompt || 'No prompt')}<br>Context: ${esc(t.context || 'Not recorded')}</p><p class="selection-note">Control predictions are locked and hidden until you save this observation. They do not receive this response or the objective answer.</p>
    <div class="two-cols"><label>Participation / outcome<select name="outcome" id="observation-outcome"><option value="response">Selection observed</option><option value="no_response">No response</option><option value="withdrawal">Participant withdrew · end session</option><option value="distress">Distress observed · end session</option></select></label><label>Observed selection<select name="choice" id="observation-choice"><option value="">Select the observed symbol</option>${t.display_order.map(c => `<option>${esc(c)}</option>`).join('')}</select></label></div>
    <div class="two-cols"><label>Corroboration · against your locked criterion<select name="corroboration" id="observation-corroboration"><option value="unknown">Unknown / not yet assessed</option><option value="yes">Criterion met</option><option value="no">Criterion not met</option><option value="not_applicable">Not applicable</option></select></label><label>Latency in seconds · optional<input name="latency_seconds" type="number" min="0" max="86400" step="0.1"></label></div><label><input name="initiated" type="checkbox">Interaction initiated by the participant</label><label>Behavioral notes<textarea name="notes" maxlength="4000" placeholder="Describe observable behavior, including contradictory or ambiguous evidence."></textarea></label><label>Media reference · optional<input name="media_reference" maxlength="500" placeholder="Recording filename and timestamp; no media is uploaded"></label><p class="small">Saved observations are immutable in this version. Unknown remains unknown; use external notes for later adjudication. Review before saving.</p><button type="submit" class="primary">Save observation</button></form>`;
}
function outcomeChanged() {
  const responded = $('#observation-outcome').value === 'response';
  $('#observation-choice').disabled = !responded;
  if (!responded) { $('#observation-choice').value = ''; $('#observation-corroboration').value = 'not_applicable'; }
  $('#observation-corroboration').disabled = !responded;
}
async function recordObservation(event) {
  event.preventDefault(); const form = event.target, data = new FormData(form);
  const pending = currentStudy.trials.find(t => t.status === 'pending');
  await safely(async () => { currentStudy = await api(`/api/studies/${currentStudy.id}/trials/${pending.id}/observation`, {
    outcome:data.get('outcome'),choice:data.get('choice') || null,corroboration:data.get('corroboration') || 'not_applicable',
    initiated:data.has('initiated'),latency_seconds:data.get('latency_seconds') === '' ? null : Number(data.get('latency_seconds')),
    notes:data.get('notes'),media_reference:data.get('media_reference')}); renderStudy(); message('Observation saved.'); }, form.querySelector('button[type=submit]'));
}
function analysis(s) {
  if (s.status !== 'closed') return `<div class="note"><strong>Comparison scores appear when you close the session.</strong> This reduces feedback during observation. Individual completed traces and exports are accessible, so this is not enforced double blinding.</div>`;
  const r = s.summary;
  return `<div class="panel analysis-controls"><h2>Which explanations fit these selections?</h2><p class="small">${r.responses} recorded selections. Predictions were committed before each response. Lower scores indicate a closer match; there is no significance test. Deterministic controls assign all probability to one choice. Log loss uses a 10⁻¹⁵ floor; mismatches are also shown explicitly.</p><div class="table-wrap"><table><thead><tr><th>Comparison</th><th>Brier ↓</th><th>Log loss ↓</th><th>Responses scored</th><th>Exact matches</th><th>Zero-probability responses</th></tr></thead><tbody>${r.controls.map(c => `<tr><td>${esc(c.name)}</td><td>${c.brier === null ? '—' : c.brier.toFixed(3)}</td><td>${c.log_loss === null ? '—' : c.log_loss.toFixed(3)}</td><td>${c.n}</td><td>${c.exact_matches === null ? "—" : `${c.exact_matches} / ${c.n}`}</td><td>${c.zero_probability_responses}</td></tr>`).join('')}</tbody></table></div><p class="small">${esc(r.interpretation)}</p>${r.objective_trials ? `<p class="small">Objective selections: ${r.objective_correct} of ${r.objective_trials} matched the predeclared answer. Free-choice trials have no correct answer.</p>` : ''}</div>`;
}
function downloadJSON(value, filename) {
  const url = URL.createObjectURL(new Blob([JSON.stringify(value,null,2)],{type:'application/json'}));
  const a = document.createElement('a'); a.href = url; a.download = filename; a.click(); setTimeout(() => URL.revokeObjectURL(url), 2000);
}
function cumulativeChart(agents, steps, reversal) {
  const colors = {adaptive:'#305c43',frozen:'#b8964f',chance:'#7e9cab',deterministic:'#805691',det_frozen:'#b86c48'}, max = Math.max(...Object.values(agents).map(a => a.total_reward),1);
  const x = i => 45 + i / steps * 700, y = value => 210 - value / max * 165;
  return `<svg class="chart" viewBox="0 0 780 250" role="img" aria-label="Cumulative reward over steps for stochastic, deterministic, learning-disabled, and random agents"><line x1="45" y1="210" x2="745" y2="210"/><line x1="45" y1="45" x2="45" y2="210"/><line x1="${x(reversal)}" y1="35" x2="${x(reversal)}" y2="210" stroke-dasharray="4 5"/><text x="${x(reversal)+5}" y="27">Rewards reverse</text><text x="10" y="49">${max.toFixed(0)}</text><text x="19" y="213">0</text><text x="43" y="233">0</text><text x="715" y="233">${steps} steps</text>${Object.entries(agents).map(([key,a]) => { let sum=0; const points = `45,210 ` + a.trace.map((t,i) => {sum+=t.reward;return `${x(i+1)},${y(sum)}`;}).join(' ');return `<polyline fill="none" stroke="${colors[key]}" stroke-width="2.8" points="${points}"/>`; }).join('')}</svg>`;
}
function renderSimulation() {
  const s = simulation;
  const names = {adaptive:'Stochastic learner',frozen:'Stochastic / learning disabled',chance:'Random choice',deterministic:'Deterministic learner',det_frozen:'Deterministic / learning disabled'};
  $('#simulation-result').innerHTML = `<div class="panel"><div class="study-heading"><div><span class="badge synthetic">SYNTHETIC · REPLAYABLE</span><h2>One environment. Five mechanisms.</h2></div><button class="secondary" id="export-simulation">Export full trace</button></div><p class="small">Cumulative reward. Green: stochastic learner · gold: its learning-disabled control · blue: chance · purple: deterministic learner · orange: its learning-disabled control.</p>${cumulativeChart(s.agents,s.steps,s.reverse_at)}<div class="toolbar"><label for="trace-step">Inspect step <span id="trace-step-label">1</span><input id="trace-step" class="simulation-slider" type="range" min="1" max="${s.steps}" value="1"></label></div><div class="legend"><span><i class="apple"></i>Apple</span><span><i class="music"></i>Music</span><span><i class="rest"></i>Rest</span></div></div><div class="agent-grid">${Object.entries(s.agents).map(([key,a]) => `<article class="panel"><div class="card-kicker">${a.deterministic ? 'NO RANDOM DRAWS' : key === 'chance' ? 'UNIFORM CHANCE' : 'SEEDED RANDOM EXPLORATION'} · ${a.learning_enabled ? 'LEARNING' : 'NO VALUE UPDATES'}</div><h2>${names[key]}</h2><p class="small">Total authored reward: ${a.total_reward.toFixed(2)}</p><div class="timeline" aria-label="${names[key]} choices">${a.trace.map(t => `<span class="${t.choice}" title="Step ${t.step}: ${t.choice}"></span>`).join('')}</div><div id="agent-${key}"></div></article>`).join('')}</div><details class="panel"><summary>Inspect the rules</summary><pre class="trace">${esc(JSON.stringify(s.rules,null,2))}</pre></details><p class="small">${esc(s.interpretation)}</p>`;
  $('#trace-step').addEventListener('input', renderStep); renderStep();
}
function renderStep() {
  const i = Number($('#trace-step').value) - 1;
  $('#trace-step-label').textContent = i+1;
  Object.entries(simulation.agents).forEach(([key,a]) => {
    const t = a.trace[i];
    $(`#agent-${key}`).innerHTML = `<h3>Chose ${esc(t.choice)} · reward ${t.reward.toFixed(2)}</h3><p class="small">${esc(t.phase)} · ${esc(t.reason)}</p><p class="small">Fatigue: ${t.state_before.fatigue.toFixed(2)} → ${t.state_after.fatigue.toFixed(2)}</p>${Object.entries(t.state_after.values).map(([c,v]) => `<div class="small">${esc(c)} learned value · ${v.toFixed(3)}</div><div class="bar"><span style="width:${Math.max(0,Math.min(100,v*100))}%"></span></div>`).join('')}<details><summary>Full decision trace</summary><pre class="trace">${esc(JSON.stringify(t,null,2))}</pre></details>`;
  });
}
document.addEventListener('click', event => {
  const button = event.target.closest('button');
  if (!button) return;
  if (button.dataset.view) return navigate(button.dataset.view);
  if (button.classList.contains('open-study')) return safely(() => openStudy(button.dataset.id), button);
  if (button.dataset.move) {
    const index=Number(button.dataset.index), next=index+Number(button.dataset.move);
    const saved=Object.fromEntries(readFeatures().map(f => [f.choice,f]));
    [displayOrder[index],displayOrder[next]]=[displayOrder[next],displayOrder[index]]; renderFeatureRows(saved); return;
  }
  if (['home-new','new-study','empty-new'].includes(button.id)) return newStudy();
  if (button.id === 'cancel-study') return $('#create-dialog').close();
  if (button.id === 'back-studies') { currentStudy=null; return safely(loadStudies); }
  if (button.id === 'demo') return safely(async () => { const s=await api('/api/demo',{}); currentStudy=null; navigate('studies'); await openStudy(s.id); },button);
  if (button.id === 'close-study') return safely(async () => { currentStudy=await api(`/api/studies/${currentStudy.id}/close`,{});renderStudy(); },button);
  if (button.id === 'export-simulation') return downloadJSON(simulation,`agent-sandbox-seed-${simulation.seed}.json`);
  if (button.id === 'quit') return safely(async () => { await api('/api/shutdown',{}); document.querySelector('main').innerHTML='<div class="panel"><h1>See you next time.</h1><p>Bird Voice Lab has stopped. Your records are saved. You can close this browser tab.</p></div>'; },button);
});
$('#study-form').addEventListener('submit', event => {
  event.preventDefault();const data=new FormData(event.target);
  safely(async () => { const s=await api('/api/studies',{title:data.get('title'),subject:data.get('subject'),question:data.get('question'),criterion:data.get('criterion'),choices:data.get('choices').split('\n').map(c=>c.trim()).filter(Boolean),seed:Number(data.get('seed')),max_trials:Number(data.get('max_trials'))});$('#create-dialog').close();event.target.reset();currentStudy=null;navigate('studies');await openStudy(s.id);},event.target.querySelector('button[type=submit]'));
});
$('#simulation-form').addEventListener('submit', event => {
  event.preventDefault();const data=new FormData(event.target);
  safely(async () => {simulation=await api('/api/simulate',Object.fromEntries([...data.entries()].map(([k,v])=>[k,Number(v)])));renderSimulation();},event.target.querySelector('button[type=submit]'));
});
$('.brand').addEventListener('click', event=>{event.preventDefault();navigate('home');});
safely(loadStudies);
