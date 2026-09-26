/* Additive Radar presentation. Analysis, ordering and geometry remain upstream. */
(() => {
  const workspace = document.getElementById('layout');
  workspace.classList.add('radar-scope', 'radar-workspace');
  const inspector = document.getElementById('detailPanel');
  inspector.classList.add('radar-inspector');
  inspector.setAttribute('aria-label', 'Opportunity inspector');
  workspace.append(inspector);
  const toolbar = document.createElement('div');
  toolbar.className = 'radar-scope radar-toolbar';
  toolbar.innerHTML = '<div class="radar-title"><h1>Coordination Radar</h1><small>Cross-utility opportunities · geography first</small></div>';
  const toolbarTools = document.createElement('div');
  toolbarTools.className = 'radar-toolbar-tools';
  toolbarTools.append(document.getElementById('yearControl'));
  toolbar.append(document.querySelector('.dataset-toggle'), toolbarTools);
  document.getElementById('radarToolbar').classList.add('radar-legacy-toolbar');
  const banner = document.getElementById('dataBanner');
  banner.classList.add('radar-banner');
  banner.setAttribute('role', 'status');
  banner.before(toolbar);
  const list = document.getElementById('matchList');
  list.setAttribute('aria-label', 'Ranked coordination opportunities');
  const legend = document.querySelector('.legend');
  legend.innerHTML = '<details open><summary>Map key</summary>' + legend.innerHTML + '<div class="row">Dashed routes: estimated geometry</div></details>';
  const actions = document.createElement('div');
  actions.className = 'radar-map-actions';
  actions.innerHTML = '<button type="button" class="radar-action" id="radarExtent">All projects</button><button type="button" class="radar-action" id="radarFocus">Focus pair</button>';
  document.querySelector('.map-wrap').append(actions);
  const selection = L.layerGroup().addTo(map);
  const e = escapeHtml;
  const mode = () => DATASETS[currentDataset].label;
  const geometryStatus = p => currentDataset === 'demo' ? 'Demo geometry' : p.estimated_geometry ? 'Estimated geometry' : (projectParts(p).length ? 'Verified geometry' : 'Geometry unavailable');
  const timing = m => m.timeline_overlap ? 'Timing overlaps' : m.timeline_gap_years == null ? 'Timing unknown' : `${m.timeline_gap_years}-year timing gap`;
  const projectTitle = p => `<div class="radar-project-name"><span class="radar-utility ${p.utility === 'GPC' ? 'gpc' : ''}">${e(p.utility)}</span>${e(p.name)}</div>${typeAndVoltageRow(p) ? `<div class="radar-muted">${typeAndVoltageRow(p)}</div>` : ''}`;
  const statusChips = m => `<div class="radar-chips"><span class="radar-chip ${currentDataset}">${e(mode())}</span><span class="radar-chip">${e(timing(m))}</span></div>`;
  function evidence(p) {
    const field = (label, value) => `<dt>${label}</dt><dd>${e(value || 'Unavailable')}</dd>`;
    return `<section>${projectTitle(p)}<dl>${field('Geometry', geometryStatus(p))}${field('Method', p.geometry_method)}${field('Geometry confidence', p.geometry_confidence)}${field('Record confidence', p.data_confidence)}<dt>Document</dt><dd>${sourceLink(p) || 'Source unavailable'}</dd>${p.geometry_source ? `<dt>Geometry source</dt><dd>${/^https?:\/\//i.test(p.geometry_source) ? `<a href="${e(p.geometry_source)}" target="_blank" rel="noopener">View geometry source ↗</a>` : e(p.geometry_source)}</dd>` : ''}</dl>${p.geometry_notes ? `<p>${e(p.geometry_notes)}</p>` : ''}</section>`;
  }
  const originalBrief = buildCoordinationBriefText;
  buildCoordinationBriefText = function(m) {
    return originalBrief(m).replace(
      'Geographic overlap verified with deterministic GIS calculations (Gridlock coordination engine).',
      `${mode()} · Deterministic closest-point GIS analysis. ${currentDataset === 'estimated' ? 'Estimated geometry — planning-screening use only.' : currentDataset === 'demo' ? 'Illustrative demo data, not verified evidence.' : 'Human review is required before coordination decisions.'}`
    );
  };
  const originalDetail = renderDetailPanel;
  renderDetailPanel = function(m) {
    originalDetail(m); // Retain the existing scenario, timeline, and copy event contracts.
    const scenarioNode = inspector.querySelector('.scenario');
    const timelineNode = inspector.querySelector('.timeline-viz');
    const savingsNode = inspector.querySelector('.savings');
    const areasNode = inspector.querySelector('.coord-areas');
    inspector.hidden = false;
    const tier = m.distance_tier_label || m.tier_label || 'Tier unavailable';
    inspector.innerHTML = `<div class="radar-inspector-head"><h3>Opportunity ${e(m.match_id)}</h3><button type="button" class="radar-action" data-radar-close aria-label="Close opportunity details">Close ×</button></div>
      ${statusChips(m)}<section>${projectTitle(m.project_a)}<div class="radar-muted">↕ Cross-utility comparison</div>${projectTitle(m.project_b)}</section>
      <section><div class="radar-distance">${e(m.distance_km)} <small>km · closest points</small></div><p>${e(tier)}</p></section>
      <section><h4>Why this was flagged</h4><p>The measured closest-point distance is ${e(m.distance_km)} km, within the analysis tier “${e(tier)}”.</p><p>${m.timeline_overlap ? 'The source schedules overlap.' : m.timeline_gap_years == null ? 'Timing is unknown for at least one project; overlap is not assumed.' : `The source schedules do not overlap (${e(m.timeline_gap_years)}-year gap). Geography places this pair in the results.`}</p>${m.screening_note ? `<p>${e(m.screening_note)}</p>` : ''}${m.close_tier_blocked ? '<p>Geometry eligibility blocks a closer tier; this pair remains in the under-40 km screen.</p>' : ''}${currentDataset === 'estimated' ? '<p>Interpret proximity alongside the geometry methods and confidence below. Estimated routes are screening geometry.</p>' : ''}<p>Potential coordination for human investigation, not a decision that utilities must coordinate.</p></section>
      <section data-radar-schedule><h4>Schedules</h4><p>${e(m.project_a.utility)} · ${e(formatYears(m.project_a))}<br>${e(m.project_b.utility)} · ${e(formatYears(m.project_b))}</p></section>
      <section><h4>Analysis brief</h4><p style="white-space:pre-line">${e(m.coordination_brief || m.priority_explanation || 'No brief available.')}</p>${typeof m.coordination_score === 'number' ? `<p>Within-tier coordination score: ${e(m.coordination_score)}<br>${e(m.coordination_explanation || '')}</p>` : ''}<button class="copy-brief-btn" type="button" data-match-id="${e(m.match_id)}">Copy coordination brief</button></section>
      <section><h4>Opportunity evidence</h4><p>Source records and geometry provenance for this pair.</p>${evidence(m.project_a)}${evidence(m.project_b)}</section>`;
    const schedule = inspector.querySelector('[data-radar-schedule]');
    if (timelineNode) schedule.append(timelineNode);
    // Estimated analysis uses a different within-tier score: do not display the
    // verified-only simulator's undefined/NaN priority score for these records.
    if (scenarioNode && Number.isFinite(m.priority_score)) schedule.append(scenarioNode);
    if (areasNode) inspector.append(areasNode);
    if (savingsNode) inspector.append(savingsNode);
    requestAnimationFrame(() => map.invalidateSize());
  };
  function highlight(m) {
    selection.clearLayers();
    if (!m) return;
    [m.project_a, m.project_b].forEach(p => {
      const color = getVar(p.utility === 'DESC' ? '--utility-a' : '--utility-b');
      projectParts(p).forEach(part => {
        if (part.length > 1) L.polyline(part, { color, weight: 7, opacity: .95, dashArray: p.estimated_geometry ? '6 4' : null, interactive: false }).addTo(selection);
        if (part.length) L.circleMarker(part[0], { color, radius: 10, weight: 3, dashArray: p.estimated_geometry ? '4 3' : null, fillOpacity: .25, interactive: false }).addTo(selection);
      });
    });
    const a = m.closest_points?.a || m.closest_point_a;
    const b = m.closest_points?.b || m.closest_point_b;
    [a,b].filter(Boolean).forEach(p => L.circleMarker([p.lat,p.lng], { radius: 5, color: getVar('--text'), weight: 2, fillColor: getVar('--panel'), fillOpacity: 1, interactive: false }).addTo(selection));
  }
  const originalSelect = selectMatch;
  selectMatch = function(id) {
    document.getElementById('radarFocus').disabled = false;
    inspector.hidden = false;
    map.invalidateSize();
    originalSelect(id);
    highlight((analysis?.matches || []).find(m => m.match_id === id));
    list.querySelectorAll('.match-item').forEach(el => el.setAttribute('aria-pressed', String(el.dataset.matchId === id)));
  };
  const originalRender = render;
  render = function() {
    selection.clearLayers();
    workspace.removeAttribute('aria-busy');
    originalRender();
    banner.classList.add('radar-banner');
    document.querySelectorAll('.dataset-toggle button').forEach(b => b.setAttribute('aria-pressed', String(b.classList.contains('active'))));
    if (currentDataset === 'estimated') banner.textContent = 'Estimated geometry — planning-screening use only.';
    list.querySelectorAll('.match-item').forEach((el, index) => {
      const m = analysis.matches.find(m => m.match_id === el.dataset.matchId);
      if (!m) return;
      el.tabIndex = 0;
      el.setAttribute('role', 'button');
      el.setAttribute('aria-pressed', String(m.match_id === selectedMatchId));
      el.innerHTML = `<div class="radar-card-top"><span class="radar-muted">${String(index + 1).padStart(2, '0')} · OPPORTUNITY</span><span class="radar-distance">${e(m.distance_km)} <small>km</small></span></div>${projectTitle(m.project_a)}${projectTitle(m.project_b)}<div class="radar-chips"><span class="radar-chip">${e(m.distance_tier_label || m.tier_label)}</span></div>${statusChips(m)}<div class="radar-chips">${[m.project_a,m.project_b].map(p => `<span class="radar-chip">${e(p.utility)} · ${e(geometryStatus(p))} · ${e(p.geometry_confidence || 'confidence unknown')}</span>`).join('')}</div>`;
      el.addEventListener('keydown', event => { if (event.key === 'Enter' || event.key === ' ') { event.preventDefault(); selectMatch(m.match_id); } });
    });
    projectsOf(analysis).forEach(p => {
      projectMarkers.get(p.id)?.setStyle({ dashArray: p.estimated_geometry ? '4 3' : null });
    });
    matchLayers.forEach((line, id) => {
      line.on('mouseover', () => line.setStyle({ weight: 7 }));
      line.on('mouseout', () => line.setStyle({ weight: id === selectedMatchId ? 6 : 3 }));
    });
    applyYearFilter();
  };
  inspector.addEventListener('click', event => {
    if (!event.target.closest('[data-radar-close]')) return;
    const previousId = selectedMatchId;
    inspector.hidden = true;
    selectedMatchId = null;
    document.getElementById('radarFocus').disabled = true;
    selection.clearLayers();
    list.querySelectorAll('.match-item').forEach(el => { el.classList.remove('selected'); el.setAttribute('aria-pressed', 'false'); });
    matchLayers.forEach(line => line.setStyle({ weight: 3 }));
    map.invalidateSize();
    Array.from(list.querySelectorAll('.match-item')).find(el => el.dataset.matchId === previousId)?.focus();
  });
  inspector.addEventListener('keydown', event => {
    if (event.key === 'Escape') inspector.querySelector('[data-radar-close]')?.click();
  });
  document.getElementById('radarExtent').addEventListener('click', () => {
    const points = projectsOf(analysis || {}).flatMap(p => projectParts(p).flat());
    if (points.length) map.fitBounds(points, { padding: [35,35] });
  });
  document.getElementById('radarFocus').addEventListener('click', () => { if (selectedMatchId) selectMatch(selectedMatchId); });
  window.radarLoading = function(name) {
    document.querySelectorAll('.dataset-toggle button').forEach(b => b.setAttribute('aria-pressed', String(b.id === {verified: 'btnVerified', estimated: 'btnEstimated', demo: 'btnDemo'}[name])));
    selection.clearLayers();
    clearMap();
    analysis = null;
    selectedMatchId = null;
    document.getElementById('radarFocus').disabled = true;
    workspace.setAttribute('aria-busy', 'true');
    inspector.hidden = true;
    document.getElementById('stats').innerHTML = '';
    document.getElementById('listHeading').textContent = 'Ranked coordination opportunities';
    document.getElementById('yearControl').classList.add('hidden');
    list.innerHTML = `<div class="radar-state" role="status">Loading ${e(DATASETS[name].label)} opportunities…</div>`;
    banner.className = `banner visible radar-banner ${name === 'estimated' ? 'estimated' : name === 'demo' ? 'demo' : 'verified-empty'}`;
    banner.textContent = name === 'estimated' ? 'Estimated geometry — planning-screening use only.' : name === 'demo' ? 'Demo — illustrative data, not verified evidence.' : 'Loading verified analysis…';
  };
  const originalError = renderLoadErrorState;
  renderLoadErrorState = function(name, err) {
    workspace.removeAttribute('aria-busy');
    originalError(name, err);
    if (name === 'estimated') banner.textContent = 'Estimated geometry — planning-screening use only. ' + banner.textContent;
    banner.classList.add('radar-banner');
    const retry = document.createElement('button');
    retry.className = 'radar-action'; retry.textContent = 'Retry loading';
    retry.addEventListener('click', () => loadDataset(name));
    list.append(retry);
  };
  loadDataset('verified');
})();
