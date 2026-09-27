const test = require('node:test');
const assert = require('node:assert/strict');

const { geometryParts, geometryBadge, coordinationTier, initialSelection } = require('../radar-model.js');

test('geometryParts converts canonical GeoJSON into Leaflet latitude-longitude parts', () => {
  assert.deepEqual(
    geometryParts({ type: 'Point', coordinates: [-81.175112, 32.352116] }),
    [[[32.352116, -81.175112]]]
  );
  assert.deepEqual(
    geometryParts({ type: 'LineString', coordinates: [[-81.2, 32.3], [-81.1, 32.4]] }),
    [[[32.3, -81.2], [32.4, -81.1]]]
  );
  assert.deepEqual(
    geometryParts({
      type: 'MultiLineString',
      coordinates: [[[-81.2, 32.3], [-81.1, 32.4]], [[-80.9, 32.5], [-80.8, 32.6]]],
    }),
    [[[32.3, -81.2], [32.4, -81.1]], [[32.5, -80.9], [32.6, -80.8]]]
  );
});

test('geometryParts rejects malformed canonical coordinates instead of creating NaN map points', () => {
  assert.deepEqual(geometryParts({ type: 'Point', coordinates: [null, 32] }), []);
  assert.deepEqual(geometryParts({ type: 'LineString', coordinates: [[-81, 32], ['bad', 33]] }), [[[32, -81]]]);
  assert.deepEqual(geometryParts({ type: 'Polygon', coordinates: [] }), []);
});

test('geometryBadge keeps verified and estimated evidence distinct in one coverage view', () => {
  assert.deepEqual(geometryBadge({ geometry_status: 'VERIFIED' }), { label: 'Verified', className: 'verified' });
  assert.deepEqual(geometryBadge({ geometry_status: 'ESTIMATED' }), { label: 'Estimated', className: 'estimated' });
  assert.deepEqual(geometryBadge({ geometry_status: 'UNRESOLVED' }), { label: 'Unresolved', className: 'unresolved' });
});

test('coordinationTier exposes the four challenge distance bands', () => {
  assert.deepEqual(coordinationTier('must_coordinate'), {
    label: 'Must coordinate',
    shortLabel: 'Touching / crossing',
    className: 'must',
  });
  assert.equal(coordinationTier('shared_land_row').label, 'ROW / land coordination potential');
  assert.equal(coordinationTier('shared_site_logistics').label, 'Site logistics coordination potential');
  assert.equal(coordinationTier('shared_crews_equipment').label, 'Crews / equipment coordination potential');
});

test('initialSelection remembers the first opportunity but defers map focus while the radar is hidden', () => {
  assert.deepEqual(initialSelection([{ match_id: 'e001' }], true), { id: 'e001', focusNow: false });
  assert.deepEqual(initialSelection([{ match_id: 'e001' }], false), { id: 'e001', focusNow: true });
  assert.deepEqual(initialSelection([], false), { id: null, focusNow: false });
});
