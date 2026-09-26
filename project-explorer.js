const root = document.querySelector('.project-explorer');
const el = id => root.querySelector(`#pe-${id}`);
const state = { projects: [], selectedId: null, filters: {} };
const filterKeys = ['search', 'utility', 'year', 'region', 'mapping', 'confidence'];
const missing = '__not_provided__';
const present = value => value !== null && value !== undefined && value !== '' && (!Array.isArray(value) || value.length > 0);
const utilityName = value => value === 'GPC' ? 'Georgia Power' : value;
const humanize = value => String(value).replaceAll('_', ' ').replace(/^./, c => c.toUpperCase());
const year = value => typeof value === 'number' && Number.isInteger(value) ? value : null;
const timingYears = p => [p.planned_start_year, p.planned_end_year, p.in_service_year].map(year).filter(v => v !== null);

// Read-only representation checks; no projections, geometry repair, or estimates.
function hasGeometry(p) {
  const geometry = p.geometry;
  const type = geometry?.type ?? p.geometry_type;
  const coordinates = geometry?.coordinates ?? geometry;
  const point = xy => Array.isArray(xy) && xy.length >= 2 && Number.isFinite(xy[0]) && Number.isFinite(xy[1]) && Math.abs(xy[0]) <= 180 && Math.abs(xy[1]) <= 90;
  if (type === 'Point') return point(coordinates);
  if (type === 'LineString') return Array.isArray(coordinates) && coordinates.length >= 2 && coordinates.every(point);
  return false;
}
function matchesYear(p, selected) {
  if (!selected) return true;
  if (selected === missing) return timingYears(p).length === 0;
  const target = Number(selected);
  const start = year(p.planned_start_year), end = year(p.planned_end_year);
  return (start !== null && end !== null && start <= target && target <= end) || timingYears(p).includes(target);
}
function matches(p) {
  const f = state.filters;
  const searchable = [p.name, p.id, p.utility, utilityName(p.utility)].join(' ').toLocaleLowerCase();
  return (!f.search || searchable.includes(f.search.toLocaleLowerCase())) &&
    (!f.utility || p.utility === f.utility) && matchesYear(p, f.year) &&
    (!f.region || (f.region === missing ? !present(p.county_region) : p.county_region === f.region)) &&
    (!f.mapping || hasGeometry(p) === (f.mapping === 'mapped')) &&
    (!f.confidence || (f.confidence === missing ? !present(p.geometry_confidence) : p.geometry_confidence === f.confidence));
}
function node(tag, className, text) {
  const result = document.createElement(tag);
  if (className) result.className = className;
  if (text !== undefined) result.textContent = text;
  return result;
}
function timingLabel(p) {
  const start = year(p.planned_start_year), end = year(p.planned_end_year), service = year(p.in_service_year);
  const parts = [];
  if (start !== null && end !== null) parts.push(`Planned ${start === end ? start : `${start}–${end}`}`);
  else if (start !== null) parts.push(`Planned start ${start}`);
  else if (end !== null) parts.push(`Planned end ${end}`);
  if (service !== null) parts.push(`In service ${service}`);
  return parts.join(' · ');
}
function voltage(p) { return Array.isArray(p.voltage_kv) && p.voltage_kv.length ? `${p.voltage_kv.join(' / ')} kV` : ''; }
function chips(p) {
  const result = node('span', 'pe-chips');
  const mapped = hasGeometry(p);
  result.append(node('span', `pe-chip${mapped ? ' pe-chip-mapped' : ''}`, mapped ? 'Mapped' : 'Unmapped'));
  if (present(p.geometry_confidence)) {
    const style = p.geometry_confidence === 'HIGH' ? ' pe-chip-high' : p.geometry_confidence === 'MEDIUM' ? ' pe-chip-medium' : '';
    result.append(node('span', `pe-chip${style}`, `Geometry: ${p.geometry_confidence}`));
  }
  return result;
}
function option(select, value, label) { const o = node('option', '', label); o.value = value; select.append(o); }
function populateFilters() {
  for (const id of ['year', 'region', 'confidence']) while (el(id).options.length > 1) el(id).remove(1);
  const years = new Set();
  for (const p of state.projects) {
    timingYears(p).forEach(y => years.add(y));
    const start = year(p.planned_start_year), end = year(p.planned_end_year);
    if (start !== null && end !== null) for (let y = start; y <= end; y++) years.add(y);
  }
  [...years].sort((a, b) => a - b).forEach(y => option(el('year'), String(y), String(y)));
  option(el('year'), missing, 'Timing not provided');
  [...new Set(state.projects.map(p => p.county_region).filter(present))].sort().forEach(r => option(el('region'), r, r));
  option(el('region'), missing, 'Unknown / Not provided');
  [...new Set(state.projects.map(p => p.geometry_confidence).filter(present))].sort().forEach(c => option(el('confidence'), c, c));
  option(el('confidence'), missing, 'Not provided');
}
function renderSummary() {
  const projects = state.projects, mapped = projects.filter(hasGeometry).length;
  const values = [[projects.length, 'Canonical projects'], [projects.filter(p => p.utility === 'DESC').length, 'DESC'], [projects.filter(p => p.utility === 'GPC').length, 'Georgia Power'], [mapped, 'Canonical mapped'], [projects.length - mapped, 'Canonical unmapped']];
  el('summary').replaceChildren(...values.map(([count, label]) => {
    const item = node('div', 'pe-metric'); item.append(node('strong', '', String(count)), node('span', '', label)); return item;
  }));
  el('summary').hidden = false;
}
function showState(container, title, description, action) {
  const box = node('div', 'pe-state');
  const icon = node('span', 'pe-state-icon', '▦'); icon.setAttribute('aria-hidden', 'true');
  box.append(icon, node('h3', '', title), node('p', '', description));
  if (action) { const b = node('button', 'pe-action', action.label); b.type = 'button'; b.addEventListener('click', action.run); box.append(b); }
  container.replaceChildren(box);
}
function renderResults() {
  const projects = state.projects.filter(matches);
  if (!projects.some(p => p.id === state.selectedId)) { state.selectedId = null; renderDetail(); }
  el('count').textContent = `${projects.length} of ${state.projects.length} projects`;
  if (!state.projects.length) { showState(el('list'), 'No projects in the catalog', 'The canonical catalog loaded successfully but contains no project records.'); return; }
  if (!projects.length) { showState(el('list'), 'No matching projects', 'Try another search or clear filters to explore the full catalog.', { label: 'Clear filters', run: clearFilters }); return; }
  el('list').replaceChildren(...projects.map(p => {
    const card = node('button', 'pe-card'); card.type = 'button'; card.dataset.projectId = p.id;
    card.setAttribute('aria-pressed', String(p.id === state.selectedId)); card.setAttribute('aria-controls', 'pe-detail-body');
    const top = node('span', 'pe-card-top');
    top.append(node('span', `pe-utility${p.utility === 'GPC' ? ' pe-utility-gpc' : ''}`, utilityName(p.utility)));
    const arrow = node('span', '', '↗'); arrow.setAttribute('aria-hidden', 'true'); top.append(arrow);
    card.append(top, node('span', 'pe-card-name', p.name));
    const meta = [present(p.project_type) ? humanize(p.project_type) : '', voltage(p)].filter(Boolean).join(' · ');
    if (meta) card.append(node('span', 'pe-card-meta', meta));
    if (timingLabel(p)) card.append(node('span', 'pe-card-timing', timingLabel(p)));
    card.append(chips(p)); return card;
  }));
}
function section(title) {
  const s = node('section', 'pe-evidence-section'); s.append(node('h4', '', title));
  const dl = node('dl', 'pe-facts'); s.append(dl); return { section: s, facts: dl };
}
function fact(dl, label, value) {
  if (!present(value)) return;
  const row = node('div', 'pe-fact'); const dd = node('dd');
  if (value instanceof Node) dd.append(value); else dd.textContent = String(value);
  row.append(node('dt', '', label), dd); dl.append(row);
}
function evidenceLink(value) {
  try {
    const url = new URL(value);
    if (!['https:', 'http:'].includes(url.protocol) || url.username || url.password) return null;
    const a = node('a', '', value); a.href = url.href; a.target = '_blank'; a.rel = 'noopener noreferrer';
    a.setAttribute('aria-label', `${value} (opens in a new tab)`); return a;
  } catch { return null; }
}
function renderDetail() {
  const p = state.projects.find(p => p.id === state.selectedId);
  if (!p) { showState(el('detail-body'), 'No project selected', 'Select a project to inspect its timing, geography, and source evidence.'); return; }
  const intro = node('div', 'pe-detail-intro'); intro.append(node('span', 'pe-utility', utilityName(p.utility)), node('h3', '', p.name), chips(p));
  const info = section('PROJECT INFORMATION');
  [['Project name', p.name], ['Project ID', p.id], ['Utility', utilityName(p.utility)], ['Project type', present(p.project_type) ? humanize(p.project_type) : null], ['Voltage', voltage(p)], ['Planned start', p.planned_start_year], ['Planned end', p.planned_end_year], ['In-service year', p.in_service_year], ['Region', p.county_region], ['Status', present(p.status) ? humanize(p.status) : null], ['Status as of source', p.status_as_of_source]].forEach(([k, v]) => fact(info.facts, k, v));
  if (!timingYears(p).length) info.section.append(node('p', 'pe-note', 'Project timing is not provided in this record.'));
  const geo = section('GEOGRAPHY');
  [['Mapping', hasGeometry(p) ? 'Mapped — canonical geometry available' : 'Unmapped — no usable canonical geometry'], ['Geometry type', p.geometry_type], ['Geometry method', p.geometry_method], ['Geometry confidence', p.geometry_confidence]].forEach(([k, v]) => fact(geo.facts, k, v));
  geo.section.append(node('p', 'pe-note', hasGeometry(p) ? 'Mapping availability does not imply surveyed geometry or high confidence.' : 'This project remains in the catalog. No usable canonical geometry is available for geographic comparison; estimated geometry is not included here.'));
  if (present(p.geometry_notes)) geo.section.append(node('p', 'pe-note', p.geometry_notes));
  const source = section('SOURCE & EVIDENCE');
  [['Source page', p.source_page], ['Source URL', evidenceLink(p.source_url)], ['Source scope', p.source_scope], ['Source project name', p.source_project_name], ['Geometry source', evidenceLink(p.geometry_source)], ['Source owner label', p.source_owner_label], ['Ownership provenance', p.ownership_provenance_note], ['Utility attribution confidence', p.utility_attribution_confidence], ['Record confidence', p.data_confidence]].forEach(([k, v]) => fact(source.facts, k, v));
  if (p.status_verification_needed === true) source.section.append(node('p', 'pe-warning', 'Status verification needed — this source record flags the project status for further verification.'));
  el('detail-body').replaceChildren(intro, info.section, geo.section, source.section);
}
function readFilters() { state.filters = Object.fromEntries(filterKeys.map(k => [k, el(k).value.trim()])); renderResults(); }
function clearFilters() { filterKeys.forEach(k => { el(k).value = ''; }); readFilters(); }
async function loadCatalog() {
  el('controls').disabled = true; el('summary').hidden = true; el('results').setAttribute('aria-busy', 'true');
  el('count').textContent = 'Loading catalog…'; state.selectedId = null; state.projects = []; renderDetail();
  showState(el('list'), 'Loading project catalog', 'Reading canonical project records.');
  try {
    const response = await fetch('./data/verified_projects.json');
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    const projects = await response.json();
    if (!Array.isArray(projects) || projects.some(p => !p || typeof p.id !== 'string' || typeof p.name !== 'string' || typeof p.utility !== 'string') || new Set(projects.map(p => p.id)).size !== projects.length) throw new Error('Unexpected canonical catalog structure');
    state.projects = projects; populateFilters(); renderSummary(); el('controls').disabled = false; clearFilters();
  } catch {
    el('count').textContent = 'Catalog unavailable';
    showState(el('list'), 'Could not load project catalog', 'The canonical data could not be read. Serve this folder over HTTP and check data/verified_projects.json, then retry.', { label: 'Retry', run: loadCatalog });
  } finally { el('results').setAttribute('aria-busy', 'false'); }
}
el('filter-form').addEventListener('submit', event => event.preventDefault());
el('search').addEventListener('input', readFilters);
filterKeys.filter(k => k !== 'search').forEach(k => el(k).addEventListener('change', readFilters));
el('clear').addEventListener('click', clearFilters);
el('list').addEventListener('click', event => {
  const card = event.target.closest('button[data-project-id]');
  if (!card) return;
  state.selectedId = card.dataset.projectId;
  el('list').querySelectorAll('button[data-project-id]').forEach(b => b.setAttribute('aria-pressed', String(b.dataset.projectId === state.selectedId)));
  renderDetail(); el('detail-title').focus({ preventScroll: true });
  if (matchMedia('(max-width: 760px)').matches) el('detail').scrollIntoView({ block: 'start' });
});
loadCatalog();
