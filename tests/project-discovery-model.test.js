const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const M = require('../project-discovery-model.js');

const proj = (id, name, extra = {}) => ({ id, name, utility: 'DESC', geometry_status: 'ESTIMATED', geometry: { type: 'Point', coordinates: [-81, 32] }, voltage_kv: [115], ...extra });
const gpc = (id, name, extra = {}) => proj(id, name, { utility: 'GPC', ...extra });
const opp = (id, a, b, tier, extra = {}) => ({ match_id: id, project_a_id: a, project_b_id: b, geographic_tier: tier, distance_km: 5, timeline_gap_years: 0, timeline_overlap: true,
  overlap_years: [2028, 2028], years_a: [2028, 2028], years_b: [2028, 2028], coordination_score: 10, ...extra });
const ids = r => r.ranked.map(e => e.matchId);

test('latestYear: in-service, then planned end, then planned start; missing is never a year', () => {
  assert.equal(M.latestYear({ in_service_year: 2030, planned_end_year: 2028 }).year, 2030);
  assert.equal(M.latestYear({ planned_end_year: 2028, planned_start_year: 2026 }).label, 'Planned end');
  assert.equal(M.latestYear({ planned_start_year: 2026 }).label, 'Planned start');
  assert.equal(M.latestYear({ in_service_year: 0, planned_end_year: null, planned_start_year: '2027' }), null);
});

test('a stronger proximity tier always outranks better timing, distance and score', () => {
  const P = [proj('a', 'A'), gpc('b', 'B'), proj('c', 'C'), gpc('d', 'D')];
  const r = M.rankOpportunities(P, [
    opp('far', 'a', 'b', 'shared_crews_equipment', { distance_km: 1, coordination_score: 99 }),
    opp('touch', 'c', 'd', 'must_coordinate', { distance_km: 0, coordination_score: -10, timeline_overlap: false, timeline_gap_years: 2, overlap_years: [] }),
  ]);
  assert.deepEqual(ids(r), ['touch', 'far']);
});

test('within a tier, overlapping schedules beat a gap, then closer distance, then score', () => {
  const P = [proj('a', 'A'), gpc('b', 'B'), gpc('c', 'C'), gpc('d', 'D'), gpc('e', 'E')];
  const t = 'shared_crews_equipment';
  const r = M.rankOpportunities(P, [
    opp('gap1-close', 'a', 'b', t, { distance_km: 2, timeline_overlap: false, timeline_gap_years: 1, overlap_years: [] }),
    opp('overlap-far', 'a', 'c', t, { distance_km: 30 }),
    opp('overlap-near', 'a', 'd', t, { distance_km: 10 }),
    opp('overlap-near-score', 'a', 'e', t, { distance_km: 10, coordination_score: 20 }),
  ]);
  assert.deepEqual(ids(r), ['overlap-near-score', 'overlap-near', 'overlap-far', 'gap1-close']);
});

test('recency, names and ID break remaining ties; order is independent of input order', () => {
  const P = [proj('a', 'Alpha', { in_service_year: 2027 }), proj('a2', 'Alpha Two', { in_service_year: 2027 }), proj('z', 'Zed', { in_service_year: 2031 }), gpc('g', 'G', { in_service_year: 2026 })];
  const M1 = [opp('m1', 'a', 'g', 'shared_crews_equipment'), opp('m2', 'a2', 'g', 'shared_crews_equipment'), opp('m3', 'z', 'g', 'shared_crews_equipment')];
  const one = ids(M.rankOpportunities(P, M1));
  assert.deepEqual(one, ['m3', 'm1', 'm2']);
  assert.deepEqual(ids(M.rankOpportunities([...P].reverse(), [...M1].reverse())), one);
});

test('DESC is always on the left and the arrow joins exactly two different utilities', () => {
  const P = [proj('a', 'A'), gpc('b', 'B')];
  const r = M.rankOpportunities(P, [opp('m1', 'b', 'a', 'shared_land_row', { years_a: [2030, 2031], years_b: [2028, 2028] })]);
  assert.equal(r.ranked[0].left.id, 'a');
  assert.equal(r.ranked[0].right.id, 'b');
  assert.deepEqual(r.ranked[0].leftSpan, [2028, 2028], 'years follow the project, not the original A/B slot');
});

test('invalid or duplicate opportunities are ignored, never invented', () => {
  const P = [proj('a', 'A'), gpc('b', 'B'), proj('c', 'C')];
  const good = opp('m1', 'a', 'b', 'shared_crews_equipment');
  const r = M.rankOpportunities(P, [good, { ...good }, opp('m2', 'a', 'ghost', 'must_coordinate'), opp('m3', 'a', 'a', 'must_coordinate'), opp('m4', 'a', 'c', 'must_coordinate'), null]);
  assert.equal(r.ignored, 5);
  assert.deepEqual(ids(r), ['m1']);
});

test('explanations say what decided each position', () => {
  const P = [proj('a', 'A'), gpc('b', 'B'), gpc('c', 'C')];
  const r = M.rankOpportunities(P, [opp('m1', 'a', 'b', 'shared_crews_equipment', { distance_km: 3 }), opp('m2', 'a', 'c', 'shared_crews_equipment', { distance_km: 9 })]);
  assert.match(r.ranked[0].why, /Ahead of #2 on distance/);
  assert.match(r.ranked[1].why, /Behind #1 on distance/);
  assert.match(r.ranked[1].why, /Ties #1 on proximity tier, timing/);
});

test('descriptions use the challenge wording and only saved facts', () => {
  const P = [proj('a', 'A'), gpc('b', 'B')];
  const r = M.rankOpportunities(P, [opp('m1', 'a', 'b', 'shared_site_logistics', { timeline_overlap: false, timeline_gap_years: 2, overlap_years: [] })]);
  assert.match(r.ranked[0].meaning, /Under 8 km.*laydown yards/);
  assert.equal(r.ranked[0].timing, 'Their schedules are 2 years apart.');
  const missing = M.rankOpportunities(P, [opp('m1', 'a', 'b', 'shared_crews_equipment', { timeline_overlap: false, timeline_gap_years: null })]).ranked[0];
  assert.equal(missing.timing, 'The timing gap is not recorded.');
});

test('proximity marker stays inside its saved tier zone; timing bars share one axis', () => {
  const P = [proj('a', 'A'), gpc('b', 'B')];
  const at = (tier, km) => M.rankOpportunities(P, [opp('m', 'a', 'b', tier, { distance_km: km })]).ranked[0];
  const zone = (e, i) => { const x = M.proximityMarker(e); return x >= i * 50 && x <= (i + 1) * 50; };
  assert.ok(zone(at('must_coordinate', 0), 0) && zone(at('shared_land_row', 1.2), 1) && zone(at('shared_site_logistics', 7.9), 2) && zone(at('shared_crews_equipment', 39.9), 3));
  assert.equal(M.proximityMarker(at('shared_crews_equipment', null)), null);
  const bars = M.timingBars(M.rankOpportunities(P, [opp('m', 'a', 'b', 'shared_crews_equipment', { years_a: [2027, 2029], years_b: [2029, 2030] })]).ranked[0]);
  assert.ok(bars.overlap && bars.overlap.w > 0 && bars.left.x === 0 && bars.right.x + bars.right.w <= 200.0001);
  assert.equal(M.timingBars(M.rankOpportunities(P, [opp('m', 'a', 'b', 'shared_crews_equipment', { years_a: null })]).ranked[0]), null);
});

test('safeHttpUrl only allows plain http(s) links', () => {
  assert.equal(M.safeHttpUrl('https://example.com/a.pdf'), 'https://example.com/a.pdf');
  for (const bad of ['javascript:alert(1)', 'https://user:pw@example.com', 'OpenStreetMap', null]) assert.equal(M.safeHttpUrl(bad), null);
});

test('real canonical publication: 24 ranked pairs, 16 projects, tier is the primary key', () => {
  const dir = path.join(__dirname, '..', 'data', 'published');
  const master = JSON.parse(fs.readFileSync(path.join(dir, 'gridlock_master_projects.json'), 'utf8'));
  const web = JSON.parse(fs.readFileSync(path.join(dir, 'website_data.json'), 'utf8'));
  const projects = master.projects.map(p => ({ ...p, ...p.source_metadata, id: p.project_id, name: p.project_name, voltage_kv: p.voltage, geometry: p.analysis_geometry }));
  const r = M.rankOpportunities(projects, web.modes.full.matches);
  assert.equal(r.ranked.length, 24);
  assert.equal(r.ignored, 0);
  assert.equal(r.byProject.size, 16);
  assert.ok(r.ranked.every(e => e.left.utility === 'DESC' && e.right.utility === 'GPC'));
  const tiers = r.ranked.map(e => e.tier.rank);
  assert.deepEqual(tiers, [...tiers].sort((a, b) => b - a));
  assert.deepEqual(ids(M.rankOpportunities([...projects].reverse(), [...web.modes.full.matches].reverse())), ids(r));
});
