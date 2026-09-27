'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const I = require('../project-discovery-model.js').impact;

test('only e001, e002, e007 and e009 have an estimate', () => {
  assert.deepEqual(Object.keys(I.ESTIMATES).sort(), ['e001', 'e002', 'e007', 'e009']);
  ['e003', 'e004', 'e005', 'e006', 'e008', 'e010', 'e024', '', null, undefined, 'constructor', '__proto__', 'toString'].forEach(id => assert.equal(I.get(id), null));
});

test('every low/base/high value equals basis x rate x shareable fraction', () => {
  Object.values(I.ESTIMATES).forEach(e => { assert.equal(e.eligibleWorkBasisUsd, 10000000); assert.ok(I.verify(e), e.matchId); assert.ok(e.lowUsd < e.baseUsd && e.baseUsd < e.highUsd); });
  assert.deepEqual(['e001', 'e002', 'e007', 'e009'].map(id => I.get(id).baseUsd), [210000, 120000, 90000, 90000]);
});

test('formatting, wording and source links', () => {
  assert.equal(I.usd(60000), '$60,000');
  assert.equal(I.pct(0.021), '2.1%');
  assert.equal(I.pct(0.0015), '0.15%');
  assert.equal(I.pct(0.0225), '2.25%');
  assert.match(I.NORMALIZATION, /illustrative \$10 million/i);
  assert.equal(I.SOURCES.length, 3);
  I.SOURCES.forEach(s => assert.match(s.url, /^https:\/\//));
  Object.values(I.ESTIMATES).forEach(e => assert.match(e.estimateLabel, /^Potential avoided/));
  Object.values(I.ESTIMATES).forEach(e => {
    assert.ok(e.savedEvidence.length >= 4);
    assert.ok(e.coordinationCandidates.length >= 4);
    assert.match(e.assumption, /scenario assumption, not an industry benchmark/i);
  });
  assert.match(I.METHODOLOGY_BODY, /local cost data/i);
  assert.match(I.METHODOLOGY_BODY, /None of those sources supplies GridLock/i);
  assert.ok(!/guarantee/i.test(JSON.stringify(I)));
});

test('estimated projects and distances match the saved canonical opportunities', () => {
  const w = JSON.parse(fs.readFileSync(path.join(__dirname, '..', 'data', 'published', 'website_data.json'), 'utf8'));
  const names = Object.fromEntries(w.projects.map(p => [p.id, p.name]));
  const ms = Object.values(w.modes).flatMap(m => (m && m.matches) || []);
  Object.values(I.ESTIMATES).forEach(e => {
    const m = ms.find(x => x.match_id === e.matchId); assert.ok(m, e.matchId);
    assert.deepEqual([names[m.project_a_id], names[m.project_b_id]].sort(), [...e.projects].sort());
    assert.equal(m.distance_km, e.distanceKm);
  });
});
