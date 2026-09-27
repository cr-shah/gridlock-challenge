(function (root, factory) {
  const api = factory();
  if (typeof module === 'object' && module.exports) module.exports = api;
  if (root) root.GridLockRadarModel = api;
})(typeof window !== 'undefined' ? window : null, function () {
  const TIERS = {
    must_coordinate: { label: 'Must coordinate', shortLabel: 'Touching / crossing', className: 'must' },
    touching_crossing: { label: 'Must coordinate', shortLabel: 'Touching / crossing', className: 'must' },
    shared_land_row: { label: 'ROW / land coordination potential', shortLabel: '< 1.6 km', className: 'land' },
    shared_land: { label: 'ROW / land coordination potential', shortLabel: '< 1.6 km', className: 'land' },
    shared_site_logistics: { label: 'Site logistics coordination potential', shortLabel: '< 8 km', className: 'logistics' },
    shared_logistics: { label: 'Site logistics coordination potential', shortLabel: '< 8 km', className: 'logistics' },
    shared_crews_equipment: { label: 'Crews / equipment coordination potential', shortLabel: '< 40 km', className: 'crews' },
    shared_crews: { label: 'Crews / equipment coordination potential', shortLabel: '< 40 km', className: 'crews' },
  };

  const finitePair = pair => Array.isArray(pair) && pair.length >= 2 &&
    Number.isFinite(pair[0]) && Number.isFinite(pair[1]);
  const toLatLng = pair => [pair[1], pair[0]];

  function geometryParts(geometry) {
    if (!geometry || typeof geometry !== 'object') return [];
    if (geometry.type === 'Point') return finitePair(geometry.coordinates) ? [[toLatLng(geometry.coordinates)]] : [];
    if (geometry.type === 'LineString') {
      const line = Array.isArray(geometry.coordinates) ? geometry.coordinates.filter(finitePair).map(toLatLng) : [];
      return line.length ? [line] : [];
    }
    if (geometry.type === 'MultiLineString') {
      if (!Array.isArray(geometry.coordinates)) return [];
      return geometry.coordinates.map(line => Array.isArray(line) ? line.filter(finitePair).map(toLatLng) : []).filter(line => line.length);
    }
    return [];
  }

  function geometryBadge(project) {
    const status = project && (project.geometry_status || (project.estimated_geometry ? 'ESTIMATED' : project.geometry ? 'VERIFIED' : 'UNRESOLVED'));
    if (status === 'VERIFIED') return { label: 'Verified', className: 'verified' };
    if (status === 'ESTIMATED') return { label: 'Estimated', className: 'estimated' };
    return { label: 'Unresolved', className: 'unresolved' };
  }

  function coordinationTier(key) {
    return TIERS[key] || { label: 'Coordination opportunity', shortLabel: 'Distance tier', className: 'unknown' };
  }

  function initialSelection(matches, radarHidden) {
    const id = Array.isArray(matches) && matches.length ? matches[0].match_id : null;
    return { id, focusNow: Boolean(id) && !radarHidden };
  }

  return { geometryParts, geometryBadge, coordinationTier, initialSelection };
});
