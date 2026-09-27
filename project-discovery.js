/* GridLock — Coordination Leaderboard UI. Read-only: data comes from GridLockData; ranking from GridLockDiscoveryModel. */
(() => {
  'use strict';
  const M = window.GridLockDiscoveryModel, R = window.GridLockRadarModel;
  const $ = id => document.getElementById(id);
  const reduced = matchMedia('(prefers-reduced-motion: reduce)');
  const SVG_NS = 'http://www.w3.org/2000/svg';
  const state = { projects: [], byId: new Map(), ranked: [], byProject: new Map(), cards: new Map(), open: new Set(), loaded: false };

  function node(tag, cls, text) {
    const n = document.createElement(tag);
    if (cls) n.className = cls;
    if (text !== undefined && text !== null) n.textContent = text;
    return n;
  }
  function svgNode(tag, attrs, cls) {
    const n = document.createElementNS(SVG_NS, tag);
    Object.entries(attrs || {}).forEach(([k, v]) => n.setAttribute(k, String(v)));
    if (cls) n.setAttribute('class', cls);
    return n;
  }
  const plural = (n, one, many) => `${n} ${n === 1 ? one : many}`;
  const behavior = () => (reduced.matches ? 'auto' : 'smooth');
  const signed = n => `${n > 0 ? '+' : ''}${n}`;

  // ---- small shared pieces -------------------------------------------------
  function utilPill(p) {
    const gpc = p.utility === 'GPC', pill = node('span', `pd-util ${gpc ? 'is-gpc' : 'is-desc'}`), dot = node('i', `pd-dot ${gpc ? 'pd-dot-gpc' : 'pd-dot-desc'}`);
    dot.setAttribute('aria-hidden', 'true'); pill.append(dot, document.createTextNode(M.utilityName(p.utility)));
    return pill;
  }
  function geoBadge(p) {
    const b = R.geometryBadge(p), chip = node('span', `pd-chip pd-geo-${b.className}`, b.label);
    chip.title = M.isMapped(p) ? 'Mapped means canonical geometry exists. It does not imply surveyed or high-confidence geometry.' : 'No usable canonical geometry. Nothing has been invented.';
    return chip;
  }
  function tierBadge(tier) { const c = node('span', `pd-chip pd-tier is-${tier.className}`, tier.brief); c.title = tier.label; return c; }
  function timingLabel(p) {
    const s = p.planned_start_year, e = p.planned_end_year, v = p.in_service_year, out = [], ok = Number.isInteger;
    if (ok(s) && ok(e)) out.push(`Planned ${s === e ? s : `${s}–${e}`}`); else if (ok(s)) out.push(`Planned start ${s}`); else if (ok(e)) out.push(`Planned end ${e}`);
    if (ok(v)) out.push(`In service ${v}`);
    return out.join(' · ');
  }
  const voltageLabel = p => (Array.isArray(p.voltage_kv) && p.voltage_kv.length ? `${p.voltage_kv.join(' / ')} kV` : '');
  const metaLine = p => [M.present(p.project_type) ? M.humanize(p.project_type) : '', voltageLabel(p)].filter(Boolean).join(' · ');
  function stateBox(title, text, action, icon) {
    const box = node('div', 'pd-state'), i = node('span', 'pd-state-icon', icon || '▦');
    box.setAttribute('role', 'status'); i.setAttribute('aria-hidden', 'true'); box.append(i, node('h3', '', title), node('p', '', text));
    if (action) { const b = node('button', 'pd-btn', action.label); b.type = 'button'; b.addEventListener('click', action.run); box.append(b); }
    return box;
  }

  // ---- header pieces -------------------------------------------------------
  function renderStats() {
    const values = [state.ranked.length, state.byProject.size, state.ranked.filter(e => e.overlap).length, state.ranked.filter(e => e.tier.className === 'must').length];
    $('pd-stats').querySelectorAll('dd').forEach((dd, i) => {
      const target = values[i];
      if (reduced.matches || target < 2) { dd.textContent = String(target); return; }
      const t0 = performance.now(), tick = now => { const k = Math.min(1, (now - t0) / 700); dd.textContent = String(Math.round(target * (1 - Math.pow(1 - k, 3)))); if (k < 1) requestAnimationFrame(tick); };
      dd.textContent = '0'; requestAnimationFrame(tick);
    });
    const unresolved = state.projects.filter(p => !M.isMapped(p)).length, note = $('pd-scopenote');
    note.replaceChildren(document.createTextNode(`${unresolved} of ${state.projects.length} projects have no usable geometry, so they can’t appear in a spatial opportunity. `));
    const a = node('a', '', 'Browse all projects in the Project Explorer'); a.href = './project-explorer.html'; note.append(a, document.createTextNode('.'));
  }
  function renderHow() {
    const crit = M.CRITERIA, recipe = $('pd-recipe');
    recipe.replaceChildren(...crit.slice(0, 5).map(c => { const li = node('li'); li.append(node('span', '', c.short)); return li; }));
    const ol = node('ol');
    crit.filter(c => !['name', 'id'].includes(c.id)).forEach(c => { const li = node('li'); li.append(node('strong', '', c.label), node('span', '', c.detail)); ol.append(li); });
    const last = node('li'); last.append(node('strong', '', 'Then names, then opportunity ID'), node('span', '', 'Stable tie-breakers, so the order never jumps.')); ol.append(last);
    $('pd-how-body').replaceChildren(ol, node('p', '', 'Only saved canonical opportunities are ranked. Distances, years and scores come straight from the publication and are never recalculated in the browser. Proximity is the primary signal; timing is a strong secondary signal used with it.'));
  }
  function renderLegend(present) {
    $('pd-legend').replaceChildren(...M.TIER_LEGEND.filter(t => present.has(t.className)).map(t => {
      const li = node('li'), a = node('a', `pd-chip pd-tier is-${t.className}`, `${t.shortLabel} · ${t.brief}`);
      a.href = `#pd-group-${t.className}`; a.title = `Jump to: ${t.label}`; li.append(a); return li;
    }));
  }

  // ---- the pair card -------------------------------------------------------
  function arrows() {
    const h = svgNode('svg', { viewBox: '0 0 200 26', 'aria-hidden': 'true', focusable: 'false' }, 'pd-arrow pd-arrow-h');
    h.append(svgNode('line', { x1: 20, y1: 13, x2: 180, y2: 13 }), svgNode('path', { d: 'M2 13 L22 3 V23 Z' }), svgNode('path', { d: 'M198 13 L178 3 V23 Z' }));
    const v = svgNode('svg', { viewBox: '0 0 26 60', 'aria-hidden': 'true', focusable: 'false' }, 'pd-arrow pd-arrow-v');
    v.append(svgNode('line', { x1: 13, y1: 20, x2: 13, y2: 40 }), svgNode('path', { d: 'M13 2 L3 22 H23 Z' }), svgNode('path', { d: 'M13 58 L3 38 H23 Z' }));
    return [h, v];
  }
  function projectBlock(p) {
    const gpc = p.utility === 'GPC', box = node('div', `pd-proj ${gpc ? 'is-gpc' : 'is-desc'}`);
    box.dataset.pid = p.id;
    const name = node('a', 'pd-proj-name', p.name); name.href = `./project-explorer.html?project=${encodeURIComponent(p.id)}`; name.title = 'Open this project in the Project Explorer';
    box.append(utilPill(p), name);
    if (metaLine(p)) box.append(node('span', 'pd-proj-meta', metaLine(p)));
    box.append(node('span', 'pd-proj-meta', timingLabel(p) || 'Timing not provided'));
    const badges = node('div', 'pd-badges'); badges.append(geoBadge(p));
    if (M.present(p.geometry_confidence)) badges.append(node('span', 'pd-chip', `Confidence: ${M.humanize(String(p.geometry_confidence).toLowerCase())}`));
    const n = (state.byProject.get(p.id) || []).length;
    if (n > 1) badges.append(node('span', 'pd-chip', `In ${n} opportunities`));
    box.append(badges); return box;
  }
  function proximitySignal(e) {
    const box = node('div', 'pd-signal'); box.append(node('p', 'pd-signal-title', 'PROXIMITY'));
    const s = svgNode('svg', { viewBox: '0 0 200 16', 'aria-hidden': 'true', focusable: 'false' });
    ['must', 'land', 'logistics', 'crews'].forEach((c, i) => s.append(svgNode('rect', { x: i * 50 + 1, y: 4, width: 48, height: 8, rx: 3 }, `pd-zone is-${c}${e.tier.className === c ? ' on' : ''}`)));
    const x = M.proximityMarker(e); if (x !== null) s.append(svgNode('circle', { cx: x, cy: 8, r: 5.5 }, 'pd-marker'));
    box.append(s);
    const scale = node('div', 'pd-scale'); scale.setAttribute('aria-hidden', 'true'); ['touching', '1.6 km', '8 km', '40 km'].forEach(t => scale.append(node('span', '', t))); box.append(scale);
    box.append(node('p', 'pd-signal-cap', `${M.kmText(e.distanceKm)} between closest points · ${e.tier.label}`)); return box;
  }
  function timingSignal(e) {
    const box = node('div', 'pd-signal'); box.append(node('p', 'pd-signal-title', 'TIMING'));
    const bars = M.timingBars(e);
    if (!bars) { box.append(node('p', 'pd-signal-cap', 'Year ranges for this pair are not in the saved record.')); return box; }
    const s = svgNode('svg', { viewBox: '0 0 200 30', 'aria-hidden': 'true', focusable: 'false' });
    if (bars.overlap) s.append(svgNode('rect', { x: bars.overlap.x, y: 0.5, width: bars.overlap.w, height: 29, rx: 3 }, 'pd-bar-overlap'));
    s.append(svgNode('rect', { x: bars.left.x, y: 4, width: bars.left.w, height: 9, rx: 3 }, 'pd-bar-desc'), svgNode('rect', { x: bars.right.x, y: 17, width: bars.right.w, height: 9, rx: 3 }, 'pd-bar-gpc'));
    box.append(s);
    const scale = node('div', 'pd-scale'); scale.setAttribute('aria-hidden', 'true'); scale.append(node('span', '', String(bars.start)), node('span', '', String(bars.end))); box.append(scale);
    box.append(node('p', 'pd-signal-cap', `DESC ${M.rangeText(e.leftSpan)} · Georgia Power ${M.rangeText(e.rightSpan)} · ${M.timingText(e)}`)); return box;
  }
  function pairCard(e) {
    const li = node('li', `pd-pair is-${e.tier.className}`); li.id = `pd-pair-${e.matchId}`; li.dataset.match = e.matchId;
    const head = node('div', 'pd-pair-head'), rank = node('span', 'pd-rank'); rank.append(node('span', 'pd-sr-only', 'Rank '), document.createTextNode(String(e.rank)));
    const key = node('span', 'pd-pair-key', M.kmText(e.distanceKm)), sub = node('span', 'pd-pair-sub', M.timingText(e));
    const toggle = node('button', 'pd-btn pd-btn-ghost pd-toggle', 'Show details'); toggle.type = 'button';
    toggle.setAttribute('aria-expanded', 'false'); toggle.setAttribute('aria-controls', `pd-details-${e.matchId}`);
    toggle.setAttribute('aria-label', `Show details for ${e.left.name} and ${e.right.name}`);
    toggle.addEventListener('click', () => setOpen(e, !state.open.has(e.matchId)));
    head.append(rank, tierBadge(e.tier), key, sub, toggle);
    const body = node('div', 'pd-pair-body'), link = node('div', 'pd-link');
    link.append(node('span', 'pd-link-km', M.kmText(e.distanceKm)), ...arrows(), node('span', 'pd-link-tier', e.tier.brief));
    body.append(projectBlock(e.left), link, projectBlock(e.right));
    const desc = node('p', 'pd-pair-desc'); desc.append(document.createTextNode(`${e.meaning} `), node('span', '', e.timing));
    const signals = node('div', 'pd-signals'); signals.append(proximitySignal(e), timingSignal(e));
    const details = node('div', 'pd-details'); details.id = `pd-details-${e.matchId}`; details.hidden = true;
    li.append(head, body, desc, signals, node('p', 'pd-why', `Why #${e.rank}: ${e.why}`), details);
    state.cards.set(e.matchId, { li, toggle, details, built: false });
    return li;
  }

  // ---- details (built on first open) ---------------------------------------
  function facts(rows) {
    const dl = node('dl', 'pd-facts');
    rows.forEach(([label, value, required]) => {
      const has = M.present(value); if (!has && !required) return;
      const row = node('div'), dd = node('dd', has ? '' : 'pd-missing'); if (!has) dd.textContent = 'Not provided'; else if (value instanceof Node) dd.append(value); else dd.textContent = String(value);
      row.append(node('dt', '', label), dd); dl.append(row);
    });
    return dl;
  }
  function linkOrText(value) {
    if (!M.present(value)) return null;
    const href = M.safeHttpUrl(value); if (!href) return String(value);
    const a = node('a', '', value); a.href = href; a.target = '_blank'; a.rel = 'noopener noreferrer'; a.setAttribute('aria-label', `${value} (opens in a new tab)`); return a;
  }
  function limitations(p) {
    const out = [], mapped = M.isMapped(p);
    if (!mapped) { out.push('No usable canonical geometry is recorded. No coordinates have been invented.'); if (M.present(p.unresolved_reason)) out.push(`Recorded reason: ${p.unresolved_reason}.`); }
    else {
      out.push('Mapped means canonical geometry exists. It does not imply surveyed or high-confidence geometry.');
      if (p.geometry_status === 'ESTIMATED') out.push('Estimated geometry is for planning screening only.');
      if (['LOW', 'MEDIUM'].includes(String(p.geometry_confidence).toUpperCase())) out.push(`Recorded geometry confidence is ${String(p.geometry_confidence).toLowerCase()}.`);
    }
    if (!M.timingYears(p).length) out.push('No planned or in-service year is recorded.');
    if (p.status_verification_needed === true) out.push('The source record flags this project’s status for further verification.');
    return out;
  }
  function projectColumn(p) {
    const col = node('div', `pd-col ${p.utility === 'GPC' ? 'is-gpc' : ''}`);
    col.append(utilPill(p), node('h4', '', p.name));
    col.append(facts([['Project type', M.present(p.project_type) ? M.humanize(p.project_type) : null, true], ['Voltage', voltageLabel(p), true], ['Region', p.county_region, true], ['Status', M.present(p.status) ? M.humanize(p.status) : null]]));
    col.append(node('h5', '', 'TIMING'), facts([['Planned start', Number.isInteger(p.planned_start_year) ? p.planned_start_year : null, true], ['Planned end', Number.isInteger(p.planned_end_year) ? p.planned_end_year : null, true], ['In service', Number.isInteger(p.in_service_year) ? p.in_service_year : null, true]]));
    col.append(node('h5', '', 'GEOMETRY'), facts([['Status', M.humanize(p.geometry_status.toLowerCase()), true], ['Mapping', M.isMapped(p) ? 'Mapped — canonical geometry available' : 'Unmapped — no usable canonical geometry', true], ['Method', M.present(p.geometry_method) ? M.humanize(p.geometry_method) : null],
      ['Confidence', M.present(p.geometry_confidence) ? M.humanize(String(p.geometry_confidence).toLowerCase()) : null, true], ['Notes', M.present(p.geometry_notes) ? String(p.geometry_notes).replace(/\s*Estimated geometry — planning-screening use only\.?/g, '').trim() : p.geometry_notes]]));
    col.append(node('h5', '', 'SOURCE EVIDENCE'), facts([['Source document', linkOrText(p.source_url), true], ['Source page', Number.isInteger(p.source_page) ? `Page ${p.source_page}` : null], ['Geometry source', linkOrText(p.geometry_source)], ['Record confidence', p.data_confidence]]));
    col.append(node('h5', '', 'LIMITATIONS')); const ul = node('ul', 'pd-limits'); limitations(p).forEach(t => ul.append(node('li', '', t))); col.append(ul);
    const a = node('a', 'pd-explorer-link', 'Open in the Project Explorer ↗'); a.href = `./project-explorer.html?project=${encodeURIComponent(p.id)}`; col.append(a);
    return col;
  }
  // Presentation-only planning estimate: only the match IDs in impact-estimates.js get one.
  function impactBlock(matchId) {
    const I = window.GridLockImpact, est = I && I.get(matchId); if (!est) return null;
    const box = node('div', 'pd-impact');
    box.append(node('strong', 'pd-impact-label', est.estimateLabel), node('div', 'pd-impact-range', `${I.usd(est.lowUsd)} – ${I.usd(est.highUsd)}`),
      node('div', 'pd-impact-base', `Base scenario: ${I.usd(est.baseUsd)}`), node('div', 'pd-impact-norm', I.NORMALIZATION), node('p', 'pd-impact-disclaimer', I.DISCLAIMER),
      node('p', 'pd-impact-caution', `Confidence: ${est.confidence}. ${est.caution}`), node('strong', '', 'Potentially shared:'));
    const shared = node('ul', 'pd-impact-list'); est.potentialSharedResources.forEach(r => shared.append(node('li', '', r))); box.append(shared);
    const d = node('details', 'pd-impact-method'); d.append(node('summary', '', 'Methodology and sources'), node('p', '', I.METHODOLOGY_LEAD), node('p', 'pd-impact-formula', I.METHODOLOGY_FORMULA), node('p', '', I.METHODOLOGY_BODY));
    const links = node('ul', 'pd-impact-list');
    I.SOURCES.forEach(x => { const li = node('li', ''), a = node('a', '', x.label); a.href = x.url; a.target = '_blank'; a.rel = 'noopener noreferrer'; li.append(a); links.append(li); });
    d.append(links); box.append(d); return box;
  }
  function buildDetails(e, box) {
    box.append(node('h3', '', 'SAVED ANALYSIS'));
    const analysis = node('div', 'pd-analysis');
    analysis.append(facts([['Proximity tier', e.tier.label, true], ['Closest points', M.kmText(e.distanceKm), true], ['Timing', M.timingText(e), true], ['Saved score', e.score === null ? null : signed(e.score), true], ['Score basis', e.explanation]]));
    analysis.append(node('p', 'pd-note', `What could be shared: ${e.meaning}`));
    const impact = impactBlock(e.matchId); if (impact) analysis.append(impact);
    const cols = node('div', 'pd-detail-cols'); cols.append(projectColumn(e.left), projectColumn(e.right));
    box.append(analysis, node('h3', '', 'THE TWO PROJECTS'), cols);
  }
  function setOpen(e, open) {
    const c = state.cards.get(e.matchId); if (!c) return;
    if (open && !c.built) { buildDetails(e, c.details); c.built = true; }
    c.details.hidden = !open; c.toggle.setAttribute('aria-expanded', String(open));
    c.toggle.textContent = open ? 'Hide details' : 'Show details';
    c.toggle.setAttribute('aria-label', `${open ? 'Hide' : 'Show'} details for ${e.left.name} and ${e.right.name}`);
    if (open) state.open.add(e.matchId); else state.open.delete(e.matchId);
    window.gridlockAnalystContext = { mode: 'estimated', selection: open ? { kind: 'opportunity', id: e.matchId } : null };
    window.dispatchEvent(new CustomEvent('gridlock:context', { detail: window.gridlockAnalystContext }));
  }

  // ---- board ---------------------------------------------------------------
  function renderBoard() {
    const body = $('pd-board-body'), frag = document.createDocumentFragment(), present = new Set();
    state.cards.clear(); state.open.clear();
    if (!state.ranked.length) { body.replaceChildren(stateBox('No published opportunities', 'The verified catalog has no pair that is both under 40 km apart and scheduled within two years of each other, so there is nothing to rank.', null, '∅')); renderLegend(present); return; }
    const groups = [];
    state.ranked.forEach(e => { const last = groups[groups.length - 1]; if (last && last.tier.className === e.tier.className) last.items.push(e); else groups.push({ tier: e.tier, items: [e] }); });
    groups.forEach(g => {
      present.add(g.tier.className);
      const sec = node('section', `pd-group is-${g.tier.className}`), h = node('h3', 'pd-group-head', g.tier.label); sec.id = `pd-group-${g.tier.className}`;
      h.append(node('small', '', plural(g.items.length, 'opportunity', 'opportunities')), node('p', 'pd-group-meaning', g.tier.meaning));
      const ol = node('ol', 'pd-lb'); g.items.forEach(e => ol.append(pairCard(e))); sec.append(h, ol); frag.append(sec);
    });
    body.replaceChildren(frag); renderLegend(present);
  }

  // ---- deep links ----------------------------------------------------------
  function focusNote(text, clear) {
    const bar = $('pd-focus-note'); bar.replaceChildren(node('span', '', text));
    if (clear) { const b = node('button', 'pd-btn pd-btn-ghost', 'Clear highlight'); b.type = 'button'; b.addEventListener('click', clearFocus); bar.append(b); }
    bar.hidden = false;
  }
  function clearFocus() {
    document.querySelectorAll('.is-focus').forEach(n => n.classList.remove('is-focus')); $('pd-focus-note').hidden = true;
    try { const u = new URL(location.href); u.searchParams.delete('project'); u.searchParams.delete('opportunity'); history.replaceState(null, '', u); } catch { /* best effort */ }
  }
  function applyDeepLink() {
    const q = new URLSearchParams(location.search), opp = q.get('opportunity'), pid = q.get('project');
    const reveal = list => {
      list.forEach(e => state.cards.get(e.matchId).li.classList.add('is-focus'));
      setOpen(list[0], true); state.cards.get(list[0].matchId).li.scrollIntoView({ behavior: behavior(), block: 'start' });
    };
    if (opp) {
      const e = state.ranked.find(x => x.matchId === opp);
      if (e) { reveal([e]); focusNote(`Showing opportunity ${opp}.`, true); } else focusNote(`“${opp.slice(0, 80)}” is not a published opportunity ID.`, true);
    } else if (pid) {
      const list = state.byProject.get(pid), p = state.byId.get(pid);
      if (list && list.length) {
        reveal(list); document.querySelectorAll(`.pd-proj[data-pid="${CSS.escape(pid)}"]`).forEach(n => n.classList.add('is-focus'));
        focusNote(`Highlighting the ${plural(list.length, 'opportunity', 'opportunities')} that include ${p.name}.`, true);
      } else if (p) focusNote(`${p.name} is not part of a published opportunity, so it has no place on this leaderboard. Its record is in the Project Explorer.`, true);
      else focusNote(`“${pid.slice(0, 80)}” is not a canonical project ID.`, true);
    }
  }

  // ---- load ----------------------------------------------------------------
  async function load() {
    state.loaded = false; $('pd-board').setAttribute('aria-busy', 'true'); $('pd-count').textContent = 'Loading…';
    $('pd-board-body').replaceChildren(stateBox('Building the leaderboard', 'Reading and verifying canonical project records.', null, '◌'));
    try {
      if (!window.GridLockData || !M || !R) throw new Error('Required scripts are missing');
      const [{ projects }, estimated] = await Promise.all([GridLockData.load(), GridLockData.mode('estimated')]);
      if (!Array.isArray(projects) || projects.some(p => !p || typeof p.id !== 'string' || typeof p.name !== 'string')) throw new Error('Unexpected catalog structure');
      const r = M.rankOpportunities(projects, estimated.matches);
      state.projects = projects; state.byId = new Map(projects.map(p => [p.id, p])); state.ranked = r.ranked; state.byProject = r.byProject; state.loaded = true;
      renderHow(); renderStats(); renderBoard();
      $('pd-count').textContent = plural(state.ranked.length, 'ranked opportunity', 'ranked opportunities');
      $('pd-expand').disabled = $('pd-collapse').disabled = !state.ranked.length;
      applyDeepLink();
    } catch (error) {
      $('pd-count').textContent = 'Leaderboard unavailable';
      $('pd-board-body').replaceChildren(stateBox('Could not load the leaderboard', 'The canonical data could not be verified or read. Serve this folder over HTTP (for example with python -m analyst.server), check data/published/, then retry.', { label: 'Retry', run: load }, '⚠'));
      window.console && console.error('Coordination leaderboard failed to load:', error);
    } finally { $('pd-board').setAttribute('aria-busy', 'false'); }
  }

  $('pd-expand').addEventListener('click', () => state.ranked.forEach(e => setOpen(e, true)));
  $('pd-collapse').addEventListener('click', () => state.ranked.forEach(e => setOpen(e, false)));
  load();
})();
