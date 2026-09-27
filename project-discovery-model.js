/*
 * GridLock coordination-leaderboard model.
 *
 * Pure, read-only helpers that rank the PUBLISHED coordination opportunities (project pairs).
 * Everything comes from records GridLockData has already validated: nothing here calculates
 * distances, invents opportunities, or fills in missing values.
 */
(function (root, factory) {
  const radar = (typeof module === 'object' && module.exports)
    ? require('./radar-model.js')
    : (root && root.GridLockRadarModel);
  const api = factory(radar);
  if (typeof module === 'object' && module.exports) module.exports = api;
  if (root) root.GridLockDiscoveryModel = api;
})(typeof window !== 'undefined' ? window : null, function (radar) {
  // ---- small helpers -------------------------------------------------------
  const present = v => v !== null && v !== undefined && v !== '' && (!Array.isArray(v) || v.length > 0);
  const isYear = v => Number.isInteger(v) && v >= 1900 && v <= 2200;
  const finite = v => (typeof v === 'number' && Number.isFinite(v) ? v : null);
  const humanize = v => String(v).replaceAll('_', ' ').replace(/^./, c => c.toUpperCase());
  const utilityName = v => (v === 'GPC' ? 'Georgia Power' : v === 'DESC' ? 'DESC' : String(v ?? ''));
  const compareText = (a, b) => String(a).localeCompare(String(b), 'en', { numeric: true, sensitivity: 'base' });
  const descNullLast = (a, b) => (a === b ? 0 : a === null ? 1 : b === null ? -1 : b - a);

  function safeHttpUrl(value) {
    if (typeof value !== 'string' || !value.trim()) return null;
    try {
      const url = new URL(value.trim());
      if (!['https:', 'http:'].includes(url.protocol) || url.username || url.password) return null;
      return url.href;
    } catch { return null; }
  }

  // ---- proximity tiers (reuses the Radar's tier semantics) -----------------
  const TIER_RANK = { must: 4, land: 3, logistics: 2, crews: 1 };
  const TIER_BRIEF = { must: 'Must coordinate', land: 'ROW / land', logistics: 'Site logistics', crews: 'Crews / equipment' };
  // What each tier means in practice, in the challenge brief's own words.
  const TIER_MEANING = {
    must: 'Touching or crossing: outage timing and crossing structures need to be coordinated.',
    land: 'Under 1.6 km: the projects could share the land itself (right-of-way, access roads, permits).',
    logistics: 'Under 8 km: the projects could share site logistics (laydown yards, deliveries).',
    crews: 'Under 40 km: the projects could share crews and equipment.',
    unknown: 'A published coordination opportunity.',
  };
  function tierInfo(key) {
    const t = radar.coordinationTier(key);
    return { key: key || null, className: t.className, label: t.label, brief: TIER_BRIEF[t.className] || t.label, shortLabel: t.shortLabel,
      meaning: TIER_MEANING[t.className] || TIER_MEANING.unknown, rank: TIER_RANK[t.className] || 0 };
  }
  const TIER_LEGEND = [['must', 'must_coordinate'], ['land', 'shared_land_row'], ['logistics', 'shared_site_logistics'], ['crews', 'shared_crews_equipment']].map(([, k]) => tierInfo(k));

  // ---- years ---------------------------------------------------------------
  const YEAR_FIELDS = [['in_service_year', 'In service'], ['planned_end_year', 'Planned end'], ['planned_start_year', 'Planned start']];
  function latestYear(p) {
    for (const [field, label] of YEAR_FIELDS) if (isYear(p && p[field])) return { year: p[field], field, label };
    return null;
  }
  function timingYears(p) { return YEAR_FIELDS.map(([f]) => p && p[f]).filter(isYear); }
  function isMapped(p) {
    if (!p || p.geometry_status === 'UNRESOLVED') return false;
    return radar.geometryParts(p.geometry ?? p.analysis_geometry).length > 0;
  }
  const yearSpan = value => (Array.isArray(value) && value.length === 2 && isYear(value[0]) && isYear(value[1]) && value[0] <= value[1] ? [value[0], value[1]] : null);
  const rangeText = span => (!span ? '' : span[0] === span[1] ? String(span[0]) : `${span[0]}–${span[1]}`);
  const kmText = km => (km === null ? 'Distance not recorded' : `${km.toFixed(2)} km`);

  // ---- ranking criteria ----------------------------------------------------
  // Proximity is the primary signal; timing is a strong secondary signal used with it.
  const alignmentKey = e => (e.overlap ? -1 : (e.gapYears ?? Infinity));
  function timingText(e) {
    if (e.overlap) return `Schedules overlap${e.overlapYears.length ? ` (${rangeText([Math.min(...e.overlapYears), Math.max(...e.overlapYears)])})` : ''}`;
    if (e.gapYears === null) return 'Timing gap not recorded';
    return e.gapYears === 0 ? 'No gap between schedules' : `${e.gapYears}-year gap`;
  }
  const CRITERIA = [
    { id: 'tier', label: 'Proximity tier', short: 'Proximity tier', detail: 'Touching/crossing outranks under 1.6 km, then under 8 km, then under 40 km. Nothing below can override this.',
      cmp: (a, b) => b.tier.rank - a.tier.rank, show: e => e.tier.brief },
    { id: 'timing', label: 'Timing', short: 'Timing', detail: 'Overlapping schedules first, then the smallest recorded gap in years.',
      cmp: (a, b) => alignmentKey(a) - alignmentKey(b), show: timingText },
    { id: 'distance', label: 'Distance', short: 'Distance', detail: 'Closest-point distance saved in the publication, closer first.',
      cmp: (a, b) => (a.distanceKm ?? Infinity) - (b.distanceKm ?? Infinity), show: e => kmText(e.distanceKm) },
    { id: 'score', label: 'Saved coordination score', short: 'Saved score', detail: 'The score saved in the canonical publication. It is never recalculated here.',
      cmp: (a, b) => descNullLast(a.score, b.score), show: e => (e.score === null ? 'none saved' : String(e.score)) },
    { id: 'recency', label: 'Most recent project year', short: 'Recency', detail: 'The later of the two projects’ latest years (in service, else planned end, else planned start). A missing year is never treated as recent.',
      cmp: (a, b) => descNullLast(a.latest && a.latest.year, b.latest && b.latest.year), show: e => (e.latest ? String(e.latest.year) : 'no year') },
    { id: 'name', label: 'Project names (A–Z)', short: 'Names', detail: 'Stable tie-breaker so the order never jumps.',
      cmp: (a, b) => compareText(a.left.name, b.left.name) || compareText(a.right.name, b.right.name), show: () => 'name' },
    { id: 'id', label: 'Opportunity ID', short: 'ID', detail: 'Final stable tie-breaker.', cmp: (a, b) => compareText(a.matchId, b.matchId), show: () => 'ID' },
  ];
  const compareEntries = (a, b) => { for (const c of CRITERIA) { const r = c.cmp(a, b); if (r) return r; } return 0; };

  function explain(entry, other, otherRank, leading) {
    if (!other) return 'The only published opportunity.';
    for (let i = 0; i < CRITERIA.length; i++) {
      const c = CRITERIA[i];
      if (!c.cmp(entry, other)) continue;
      if (c.id === 'name' || c.id === 'id') return `Ties #${otherRank} on every saved signal; ordered by ${c.id === 'name' ? 'project names' : 'opportunity ID'}.`;
      const tied = CRITERIA.slice(0, i).map(x => x.short.toLowerCase());
      const tie = tied.length ? `Ties #${otherRank} on ${tied.join(', ')}. ` : '';
      return `${tie}${leading ? 'Ahead of' : 'Behind'} #${otherRank} on ${c.short.toLowerCase()} (${c.show(entry)} vs ${c.show(other)}).`;
    }
    return '';
  }

  function describe(e) {
    const timing = e.overlap
      ? `Both are scheduled in the same window${e.overlapYears.length ? ` (${rangeText([Math.min(...e.overlapYears), Math.max(...e.overlapYears)])})` : ''}.`
      : e.gapYears === null ? 'The timing gap is not recorded.' : `Their schedules are ${e.gapYears} year${e.gapYears === 1 ? '' : 's'} apart.`;
    return { meaning: e.tier.meaning, timing };
  }

  // ---- the ranked list of published opportunities --------------------------
  function rankOpportunities(projects, matches) {
    const byId = new Map(projects.map(p => [p.id, p]));
    const seen = new Set(), entries = [];
    let ignored = 0;
    for (const m of Array.isArray(matches) ? matches : []) {
      const a = m && byId.get(m.project_a_id), b = m && byId.get(m.project_b_id);
      if (!a || !b || a === b || a.utility === b.utility || seen.has(m.match_id)) { ignored++; continue; }
      seen.add(m.match_id);
      const swap = a.utility === 'GPC' && b.utility !== 'GPC';   // DESC always sits on the left
      const [left, right] = swap ? [b, a] : [a, b];
      const [ly, ry] = swap ? [m.years_b, m.years_a] : [m.years_a, m.years_b];
      const years = [latestYear(left), latestYear(right)].filter(Boolean).map(y => y.year);
      entries.push({
        matchId: m.match_id, left, right, leftSpan: yearSpan(ly), rightSpan: yearSpan(ry),
        tier: tierInfo(m.geographic_tier || m.distance_tier),
        distanceKm: finite(m.geographic_distance_km ?? m.distance_km),
        gapYears: Number.isInteger(m.timeline_gap_years) ? m.timeline_gap_years : null,
        overlap: m.timeline_overlap === true,
        overlapYears: Array.isArray(m.overlap_years) ? m.overlap_years.filter(isYear) : [],
        score: finite(m.coordination_score),
        explanation: typeof m.coordination_explanation === 'string' ? m.coordination_explanation : '',
        screeningNote: typeof m.screening_note === 'string' ? m.screening_note : '',
        latest: years.length ? { year: Math.max(...years) } : null,
      });
    }
    entries.sort(compareEntries);
    const byProject = new Map();
    entries.forEach((e, i) => {
      e.rank = i + 1;
      e.why = i === 0 ? explain(e, entries[1], 2, true) : explain(e, entries[i - 1], i, false);
      Object.assign(e, describe(e));
      for (const p of [e.left, e.right]) { if (!byProject.has(p.id)) byProject.set(p.id, []); byProject.get(p.id).push(e); }
    });
    return { ranked: entries, byProject, ignored };
  }

  // Marker position (0..200) on the four-zone proximity bar. Presentation only: it places the
  // saved distance inside its saved tier zone and never produces a new distance.
  function proximityMarker(e) {
    if (e.distanceKm === null || !e.tier.rank) return null;
    const zone = { must: [0, 0], land: [0, 1.6], logistics: [1.6, 8], crews: [8, 40] }[e.tier.className];
    const index = { must: 0, land: 1, logistics: 2, crews: 3 }[e.tier.className];
    const frac = e.tier.className === 'must' ? 0.5 : Math.min(1, Math.max(0, (e.distanceKm - zone[0]) / (zone[1] - zone[0])));
    return Math.round((index * 50 + 4 + frac * 42) * 10) / 10;
  }
  // Bars for a shared year axis. A project year counts as the whole year, so single years have width.
  function timingBars(e) {
    if (!e.leftSpan || !e.rightSpan) return null;
    const start = Math.min(e.leftSpan[0], e.rightSpan[0]), end = Math.max(e.leftSpan[1], e.rightSpan[1]) + 1, len = end - start;
    const seg = s => ({ x: ((s[0] - start) / len) * 200, w: ((s[1] + 1 - s[0]) / len) * 200 });
    const os = Math.max(e.leftSpan[0], e.rightSpan[0]), oe = Math.min(e.leftSpan[1], e.rightSpan[1]) + 1;
    return { start, end: end - 1, left: seg(e.leftSpan), right: seg(e.rightSpan), overlap: oe > os ? { x: ((os - start) / len) * 200, w: ((oe - os) / len) * 200 } : null };
  }

  return { CRITERIA, TIER_LEGEND, TIER_MEANING, present, humanize, utilityName, safeHttpUrl, tierInfo, latestYear, timingYears, isMapped,
    rankOpportunities, timingText, kmText, rangeText, proximityMarker, timingBars };
});

/* Presentation-only planning estimates, keyed by match_id (window.GridLockImpact).
   NOT canonical data: nothing here is published by DESC, Georgia Power, or the pipeline,
   and data/published/ is never modified. Only the four ids below get an estimate.
   Lives in this already-served file so the pages need no extra script file. */
(function () {
  const Impact = (function () {
  'use strict';

  const OPPORTUNITY_IMPACT_ESTIMATES = {
    e001: {
      matchId: 'e001',
      projects: ['Okatie - McIntosh 115kV Tie: Add Series Reactor', 'Goshen (Savannah)–McIntosh Rebuild'],
      distanceKm: 0,
      tier: 'Must coordinate',
      timing: 'Both projects have a 2028 construction year',
      estimateLabel: 'Potential avoided mobilization cost',
      lowUsd: 60000, baseUsd: 210000, highUsd: 450000,
      eligibleWorkBasisUsd: 10000000,
      mobilizationRates: { low: 0.03, base: 0.06, high: 0.09 },
      shareableFractions: { low: 0.20, base: 0.35, high: 0.50 },
      potentialSharedResources: ['Heavy-equipment mobilization', 'Staging and site logistics', 'Outage planning', 'Commissioning and contractor scheduling'],
      confidence: 'Medium-low',
      caution: 'Both geometries use approximate verified endpoints. Confirm the shared terminal, work scope, exact schedules, and equipment requirements with the utilities.'
    },
    e002: {
      matchId: 'e002',
      projects: ['Jasper - Okatie 230 kV #2: Construct', 'Goshen (Savannah)–McIntosh Rebuild'],
      distanceKm: 4.83,
      tier: 'Shared site logistics potential',
      timing: 'Two-year timing gap: 2026 and 2028',
      estimateLabel: 'Potential avoided logistics and mobilization cost',
      lowUsd: 30000, baseUsd: 120000, highUsd: 270000,
      eligibleWorkBasisUsd: 10000000,
      mobilizationRates: { low: 0.03, base: 0.06, high: 0.09 },
      shareableFractions: { low: 0.10, base: 0.20, high: 0.30 },
      potentialSharedResources: ['Sequential use of laydown or staging areas', 'Coordinated material deliveries', 'Specialty-equipment sourcing', 'Reuse of temporary logistics infrastructure'],
      confidence: 'Medium-low',
      caution: 'The projects are two years apart. Benefits require construction phases to converge or resources to transfer sequentially. One geometry is estimated.'
    },
    e007: {
      matchId: 'e007',
      projects: ['Jasper - Okatie 230 kV #2: Construct', 'Boulevard–Deptford Reconductor'],
      distanceKm: 29.80,
      tier: 'Shared crews / equipment potential',
      timing: 'Both projects have a 2026 construction year',
      estimateLabel: 'Potential avoided crew and equipment mobilization cost',
      lowUsd: 15000, baseUsd: 90000, highUsd: 225000,
      eligibleWorkBasisUsd: 10000000,
      mobilizationRates: { low: 0.03, base: 0.06, high: 0.09 },
      shareableFractions: { low: 0.05, base: 0.15, high: 0.25 },
      potentialSharedResources: ['Specialty-contractor procurement', 'Sequential use of transmission equipment', 'Regional staging coordination', '2026 workforce scheduling'],
      confidence: 'Medium-low',
      caution: 'A shared construction year does not prove exact schedule overlap. The Boulevard–Deptford geometry is estimated.'
    },
    e009: {
      matchId: 'e009',
      projects: ['Hooks - Modoc 115/46 kV Rebuild', 'Callaway Road - Thomson Primary 500 kV'],
      distanceKm: 29.82,
      tier: 'Shared crews / equipment potential',
      timing: 'Both projects have a 2027 construction year',
      estimateLabel: 'Potential avoided crew and equipment mobilization cost',
      lowUsd: 15000, baseUsd: 90000, highUsd: 225000,
      eligibleWorkBasisUsd: 10000000,
      mobilizationRates: { low: 0.03, base: 0.06, high: 0.09 },
      shareableFractions: { low: 0.05, base: 0.15, high: 0.25 },
      potentialSharedResources: ['Regional contractor procurement', 'Sequential use of cranes and line equipment', 'Workforce and delivery planning', '2027 construction scheduling'],
      confidence: 'Medium-low',
      caution: 'The Hooks–Modoc location uses an estimated facility point. Same-year timing does not prove exact construction overlap.'
    }
  };

  const METHODOLOGY_LEAD = 'Planning scenario, not a utility-provided budget. Potential avoided cost is calculated as:';
  const METHODOLOGY_FORMULA = 'combined eligible work × mobilization allowance × potentially shareable portion.';
  const METHODOLOGY_BODY = 'The 3%–9% mobilization allowance is a cross-sector construction proxy from official FHWA cost guidance. The shareable portion is a GridLock scenario assumption based on the saved coordination tier, project timing, and resource-sharing possibilities. Low, base, and high cases are shown because the utilities have not published detailed construction budgets or coordination agreements.';
  const DISCLAIMER = 'Illustrative, non-canonical planning estimate. Not published by DESC, Georgia Power, SCRTP, SERTP, FHWA, or GAO. Validate using actual project scopes, bids, schedules, and coordination agreements.';
  const NORMALIZATION = 'Values are normalized per $10 million of combined eligible construction work.';
  const SOURCES = [
    { label: 'FHWA construction-cost guidance — mobilization 3%–9%', url: 'https://ops.fhwa.dot.gov/publications/fhwahop09021/03cost.htm' },
    { label: 'GAO cost-estimating guidance — document assumptions and sensitivity ranges', url: 'https://www.gao.gov/products/gao-20-195g' }
  ];

  const has = id => Object.prototype.hasOwnProperty.call(OPPORTUNITY_IMPACT_ESTIMATES, id);
  const get = id => (typeof id === 'string' && has(id)) ? OPPORTUNITY_IMPACT_ESTIMATES[id] : null;
  const usd = n => '$' + Math.round(n).toLocaleString('en-US');
  // basis × mobilization rate × shareable fraction (rounded to whole dollars)
  const calc = (e, k) => Math.round(e.eligibleWorkBasisUsd * e.mobilizationRates[k] * e.shareableFractions[k]);
  const verify = e => ['low', 'base', 'high'].every(k => calc(e, k) === e[k + 'Usd']);

  return { ESTIMATES: OPPORTUNITY_IMPACT_ESTIMATES, METHODOLOGY_LEAD, METHODOLOGY_FORMULA, METHODOLOGY_BODY, DISCLAIMER, NORMALIZATION, SOURCES, get, usd, calc, verify };
})();
  if (typeof window !== 'undefined') window.GridLockImpact = Impact;
  if (typeof module === 'object' && module.exports) module.exports.impact = Impact;
})();
