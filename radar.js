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
  toolbar.innerHTML = '<div class="radar-title"><h1>COORDINATION RADAR</h1><small>Discover coordination opportunities between utility transmission projects.</small></div>';
  const toolbarTools = document.createElement('div');
  toolbarTools.className = 'radar-toolbar-tools';
  toolbarTools.append(document.getElementById('yearControl'));
  const datasetSelect = document.createElement('select');
  datasetSelect.id = 'radarDataset';
  datasetSelect.setAttribute('aria-label', 'Dataset');
  datasetSelect.innerHTML = '<option value="verified">Verified</option><option value="estimated">Estimated Coverage</option>';
  datasetSelect.addEventListener('change', () => loadDataset(datasetSelect.value));
  document.querySelector('.dataset-toggle').hidden = true;
  toolbar.append(datasetSelect, toolbarTools);
  document.getElementById('radarToolbar').classList.add('radar-legacy-toolbar');
  const banner = document.getElementById('dataBanner');
  banner.classList.add('radar-banner');
  banner.setAttribute('role', 'status');
  banner.before(toolbar);
  const list = document.getElementById('matchList');
  list.setAttribute('aria-label', 'Ranked coordination opportunities');
  const yearSummary = document.createElement('p');
  yearSummary.className = 'radar-year-summary';
  yearSummary.setAttribute('role', 'status');
  yearSummary.hidden = true;
  document.getElementById('listHeading').after(yearSummary);
  function updateYearLabels() {
    list.querySelectorAll('.radar-year-group').forEach(label => label.remove());
    yearSummary.hidden = true;
    yearSummary.textContent = '';
    if (!analysis || document.getElementById('yearControl').classList.contains('hidden')) return;
    const cards = Array.from(list.querySelectorAll('.match-item'));
    // Read the existing filter's output; do not define year relevance again.
    const relevant = cards.filter(card => !card.classList.contains('hidden-by-year'));
    const other = cards.filter(card => card.classList.contains('hidden-by-year'));
    const year = document.getElementById('yearSlider').value;
    yearSummary.textContent = `${relevant.length} relevant to ${year}`;
    yearSummary.hidden = false;
    // When every card is relevant, the summary is sufficient.
    if (!other.length) return;
    const labelBefore = (card, text) => {
      const label = document.createElement('h3');
      label.className = 'radar-year-group';
      label.textContent = text;
      card.before(label);
    };
    labelBefore(other[0], `Other opportunities (${other.length})`);
  }
  const originalYearFilter = applyYearFilter;
  applyYearFilter = function() {
    originalYearFilter();
    updateYearLabels();
  };

  const legend = document.querySelector('.legend');
  legend.innerHTML = '<details><summary>ⓘ Legend</summary>' + legend.innerHTML + '<div class="row">Dashed routes: estimated geometry</div></details>';
  const actions = document.createElement('div');
  actions.className = 'radar-map-actions';
  actions.innerHTML = '<button type="button" class="radar-action" id="radarExtent">All projects</button><button type="button" class="radar-action" id="radarFocus">Focus pair</button>';
  document.querySelector('.map-wrap').append(actions);
  const rail = document.createElement('div');
  rail.className = 'radar-rail';
  const catalog = document.createElement('details');
  catalog.className = 'radar-catalog';
  catalog.innerHTML = '<summary>Browse opportunities</summary>';
  const sidebar = workspace.querySelector('.sidebar');
  const metrics = document.getElementById('stats');
  metrics.classList.add('radar-compact-metrics');
  toolbar.after(metrics);
  catalog.append(sidebar);
  rail.append(inspector, catalog);
  workspace.append(rail);
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
    const estimated = [m.project_a,m.project_b].some(p => p.estimated_geometry);
    const geometryFact = currentDataset === 'demo' ? 'Demo geometry' : estimated ? 'Estimated geometry · screening only' : 'Verified geometry';
    inspector.innerHTML = `<div class="radar-inspector-head"><h3>Opportunity ${e(m.match_id.toUpperCase())}</h3><button type="button" class="radar-action" data-radar-close aria-label="Close opportunity details">×</button></div>
      <div class="radar-distance">${e(m.distance_km)} <small>km</small></div>
      <div class="radar-chips"><span class="radar-chip ${currentDataset}">${e(mode())}</span><span class="radar-tier">${e(tier)}</span></div>
      <section class="radar-pair">${projectTitle(m.project_a)}<span aria-hidden="true">↕</span>${projectTitle(m.project_b)}</section>
      <section><h4>Why flagged</h4><ul class="radar-facts"><li>✓ Distance within 40 km</li><li>${estimated || currentDataset === 'demo' ? '◌' : '✓'} ${e(geometryFact)}</li><li>${m.timeline_overlap ? '✓ Timing overlaps' : m.timeline_gap_years == null ? '— Timing unknown' : '✕ No timing overlap'}</li></ul>${m.close_tier_blocked ? '<p>Close tier blocked · broad screening only</p>' : ''}</section>
      <details class="radar-evidence"><summary>View full evidence <span aria-hidden="true">↗</span></summary>
        <section><h4>Projects & provenance</h4>${evidence(m.project_a)}${evidence(m.project_b)}</section>
        <section data-radar-schedule><h4>Schedules</h4><p>${e(m.project_a.utility)} · ${e(formatYears(m.project_a))}<br>${e(m.project_b.utility)} · ${e(formatYears(m.project_b))}</p></section>
        <section><h4>Analysis brief</h4><p style="white-space:pre-line">${e(m.coordination_brief || m.priority_explanation || 'No brief available.')}</p>${typeof m.coordination_score === 'number' ? `<p>Within-tier score ${e(m.coordination_score)} · ${e(m.coordination_explanation || '')}</p>` : ''}<button class="copy-brief-btn" type="button" data-match-id="${e(m.match_id)}">Copy coordination brief</button></section>
      </details>`;
    const schedule = inspector.querySelector('[data-radar-schedule]');
    if (timelineNode) schedule.append(timelineNode);
    if (scenarioNode && Number.isFinite(m.priority_score)) schedule.append(scenarioNode);
    const drawer = inspector.querySelector('.radar-evidence');
    if (areasNode) drawer.append(areasNode);
    if (savingsNode) drawer.append(savingsNode);
    requestAnimationFrame(() => map.invalidateSize());
  };
  function highlight(m) {
    selection.clearLayers();
    if (!m) return;
    [m.project_a, m.project_b].forEach(p => {
      const color = getVar(p.utility === 'DESC' ? '--utility-a' : '--utility-b');
      projectParts(p).forEach(part => {
        if (part.length > 1) L.polyline(part, { color, weight: 6, opacity: .95, className: 'radar-route-pulse', dashArray: p.estimated_geometry ? '6 4' : null, interactive: false }).addTo(selection);
        if (part.length) L.circleMarker(part[0], { color, radius: 10, weight: 3, dashArray: p.estimated_geometry ? '4 3' : null, fillOpacity: .25, interactive: false }).addTo(selection);
      });
    });
    const a = m.closest_points?.a || m.closest_point_a;
    const b = m.closest_points?.b || m.closest_point_b;
    if (a && b) L.polyline([[a.lat,a.lng],[b.lat,b.lng]], { color:'#8BC4B9', weight:4, opacity:.95, dashArray:'8 10', className:'radar-connection-flow', interactive:false }).addTo(selection);
    [a,b].filter(Boolean).forEach(p => L.circleMarker([p.lat,p.lng], { radius: 5, color: getVar('--text'), weight: 2, fillColor: getVar('--panel'), fillOpacity: 1, interactive: false }).addTo(selection));
  }
  window.gridlockFocusOpportunity = (id, mode) => {
    if (mode !== currentDataset) { alert('Switch the radar to ' + mode + ' mode to view this opportunity.'); return; }
    if (!analysis?.matches?.some(m => m.match_id === id)) return;
    showView('radar'); selectMatch(id);
  };
  const originalSelect = selectMatch;
  selectMatch = function(id) {
    document.getElementById('radarFocus').disabled = false;
    inspector.hidden = false;
    map.invalidateSize();
    originalSelect(id);
    window.gridlockAnalystContext = {mode:currentDataset,selection:{kind:'opportunity',id}};
    window.dispatchEvent(new CustomEvent('gridlock:context',{detail:window.gridlockAnalystContext}));
    highlight((analysis?.matches || []).find(m => m.match_id === id));
    list.querySelectorAll('.match-item').forEach(el => el.setAttribute('aria-pressed', String(el.dataset.matchId === id)));
  };
  const originalRender = render;
  render = function() {
    selection.clearLayers();
    workspace.removeAttribute('aria-busy');
    originalRender();
    banner.classList.add('radar-banner');
    datasetSelect.value = currentDataset;
    const summary = summaryOf(analysis);
    const mapped = summary.projects_with_geometry ?? (summary.total_projects - (summary.projects_without_geometry || 0));
    const mappedLabel = currentDataset === 'verified' ? 'Verified mapped' : currentDataset === 'estimated' ? 'Mapped incl. estimates' : 'Demo mapped';
    metrics.innerHTML = [[summary.total_projects,'Projects'],[mapped,mappedLabel],[analysis.matches.length,'Opportunities']].map(([value,label]) => `<div class="stat"><span class="n">${e(value)}</span><span class="k">${e(label)}</span></div>`).join('');
    document.querySelectorAll('.dataset-toggle button').forEach(b => b.setAttribute('aria-pressed', String(b.classList.contains('active'))));
    if (currentDataset === 'estimated') banner.textContent = 'Estimated geometry — planning-screening use only.';
    list.querySelectorAll('.match-item').forEach(el => {
      const m = analysis.matches.find(m => m.match_id === el.dataset.matchId);
      if (!m) return;
      el.tabIndex = 0;
      el.setAttribute('role', 'button');
      el.setAttribute('aria-pressed', String(m.match_id === selectedMatchId));
      el.innerHTML = `<div class="radar-card-top"><span class="radar-distance">${e(m.distance_km)} <small>km</small></span><span class="radar-chip ${currentDataset}">${e(mode())}</span></div><div class="radar-card-pair" title="${e(m.project_a.name)} ↔ ${e(m.project_b.name)}"><span>${e(m.project_a.name)}</span><span aria-hidden="true">↔</span><span>${e(m.project_b.name)}</span></div><span class="radar-tier">${e(m.distance_tier_label || m.tier_label)}</span>`;
      el.addEventListener('mouseenter', () => highlight(m));
      el.addEventListener('mouseleave', () => highlight((analysis?.matches || []).find(item => item.match_id === selectedMatchId)));
      el.addEventListener('focus', () => highlight(m));
      el.addEventListener('blur', () => highlight((analysis?.matches || []).find(item => item.match_id === selectedMatchId)));
      el.addEventListener('keydown', event => { if (event.key === 'Enter' || event.key === ' ') { event.preventDefault(); selectMatch(m.match_id); } });
    });
    projectsOf(analysis).forEach(p => {
      projectMarkers.get(p.id)?.setStyle({ dashArray: p.estimated_geometry ? '4 3' : null });
    });
    matchLayers.forEach((line, id) => {
      line.on('mouseover', () => line.setStyle({ weight: 7 }));
      line.on('mouseout', () => line.setStyle({ weight: id === selectedMatchId ? 6 : 3 }));
    });
    if (!analysis.matches.length) catalog.open = true;
    applyYearFilter();
  };
  inspector.addEventListener('click', event => {
    if (!event.target.closest('[data-radar-close]')) return;
    const previousId = selectedMatchId;
    inspector.hidden = true;
    catalog.open = true;
    selectedMatchId = null;
    window.gridlockAnalystContext = {mode:currentDataset,selection:null};
    window.dispatchEvent(new CustomEvent('gridlock:context',{detail:window.gridlockAnalystContext}));
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
    window.gridlockAnalystContext = {mode:name,selection:null};
    window.dispatchEvent(new CustomEvent('gridlock:context',{detail:window.gridlockAnalystContext}));
    datasetSelect.value = name;
    yearSummary.hidden = true;
    yearSummary.textContent = '';
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
    catalog.open = true;
    metrics.innerHTML = '<div class="radar-state">Dataset unavailable</div>';
    updateYearLabels();
    if (name === 'estimated') banner.textContent = 'Estimated geometry — planning-screening use only. ' + banner.textContent;
    banner.classList.add('radar-banner');
    const retry = document.createElement('button');
    retry.className = 'radar-action'; retry.textContent = 'Retry loading';
    retry.addEventListener('click', () => loadDataset(name));
    list.append(retry);
  };
  loadDataset('estimated');
})();
