'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

const root = path.join(__dirname, '..');
const read = file => fs.readFileSync(path.join(root, file), 'utf8');

test('external pages use the stable Radar view route', () => {
  for (const file of ['project-explorer.html', 'project-discovery.html']) {
    const html = read(file);
    assert.match(html, /href="\.\/index\.html\?view=radar"/);
    assert.doesNotMatch(html, /href="\.\/index\.html#radar"/);
  }
});

test('the initial linked view is revealed only after Radar presentation setup', () => {
  const html = read('index.html');
  assert.match(html, /requestedView === 'radar'/);
  assert.match(html, /document\.documentElement\.classList\.add\('initial-radar-route'\)/);
  assert.match(html, /html\.initial-radar-route body \{ visibility: hidden; \}/);
  assert.match(html, /map\.invalidateSize\(\{ pan: false \}\);\s*document\.documentElement\.classList\.remove\('initial-radar-route'\)/);
  const radarScript = html.indexOf('<script src="radar.js"></script>');
  const initialReveal = html.indexOf('<script>openLinkedView();</script>');
  assert.ok(radarScript >= 0 && initialReveal > radarScript);
  assert.equal((html.match(/openLinkedView\(\);/g) || []).length, 1);
});

// Execute the actual render/navigation functions with a deterministic frame queue.
// This checks lifecycle ordering; it is not a substitute for Leaflet/browser QA.
function lifecycle() {
  const elements = new Map();
  const element = () => ({
    hidden: false, innerHTML: '', value: '2030', dataset: {}, children: [],
    classList: { add() {}, remove() {}, toggle() {} },
    appendChild(child) { this.children.push(child); },
    addEventListener() {}, setAttribute() {}, removeAttribute() {},
  });
  const get = id => {
    if (!elements.has(id)) elements.set(id, element());
    return elements.get(id);
  };
  get('layout').hidden = true;
  const frames = new Map();
  let nextFrame = 0;
  const focused = [];
  const context = vm.createContext({
    document: {
      getElementById: get, createElement: element,
      querySelectorAll: () => [], body: element(), documentElement: element(),
    },
    window: { scrollTo() {}, location: { search: '', hash: '' } },
    URLSearchParams,
    requestAnimationFrame(callback) { frames.set(++nextFrame, callback); return nextFrame; },
    cancelAnimationFrame: id => frames.delete(id),
    map: { invalidateSize() {}, fitBounds() {}, setView() {} },
    analysis: {
      dataset: 'estimated', summary: { total_projects: 2 },
      matches: [{ match_id: 'e001', project_a: { name: 'A', utility: 'DESC' },
        project_b: { name: 'B', utility: 'GPC' } }],
    },
    selectedMatchId: null, currentDataset: 'estimated',
    GridLockRadarModel: require('../radar-model.js'),
    clearMap() {}, summaryOf: data => data.summary, projectsOf: () => [],
    applyYearFilter() {}, getVar: () => '', TIER_COLORS: {},
    escapeHtml: String, coordinationBadge: () => '', confidenceBadge: () => '',
    selectMatch(id) {
      focused.push({ id, presentationReady: context.presentationReady, hidden: get('layout').hidden });
    },
    openMethodology() {}, closeMethodology() {}, console,
    presentationReady: false,
  });
  const html = read('index.html');
  vm.runInContext(html.slice(html.indexOf('function render() {'), html.indexOf('function selectMatch(')), context);
  vm.runInContext(html.slice(html.indexOf("let activeView = 'overview';"), html.indexOf("document.querySelectorAll('[data-view]')")), context);
  vm.runInContext(html.slice(html.indexOf('function openLinkedView() {'), html.indexOf("window.addEventListener('hashchange'")), context);
  return {
    context, focused, get,
    frame() {
      for (const [id, callback] of [...frames]) {
        if (!frames.delete(id)) continue;
        callback();
      }
    },
    load() {
      context.render();
      // radar.js finishes its synchronous presentation after originalRender().
      context.presentationReady = true;
    },
  };
}

test('Overview and external Radar entry focus only after the presentation render finishes', () => {
  for (const route of ['', '?view=radar', '#radar']) {
    const app = lifecycle();
    app.context.window.location[route.startsWith('#') ? 'hash' : 'search'] = route;
    app.context.openLinkedView();
    app.load();
    assert.equal(app.focused.length, 0, `${route || 'Overview'} must defer focus`);
    app.frame();
    if (!route) {
      assert.equal(app.focused.length, 0, 'hidden Radar must not focus');
      app.context.showView('radar');
      app.frame();
    }
    app.frame();
    assert.equal(app.focused.length, 1, 'entry and data completion share one pending refresh');
    assert.ok(app.focused.every(f => f.presentationReady && !f.hidden));
    assert.equal(app.context.selectedMatchId, 'e001');
  }
});

test('leaving Radar before its pending frame prevents hidden-map selection', () => {
  const app = lifecycle();
  app.load();
  app.context.showView('radar');
  app.context.showView('overview');
  app.frame();
  app.frame();
  assert.equal(app.focused.length, 0);
  for (let i = 0; i < 5; i++) {
    app.context.showView('radar');
    app.frame();
    app.frame();
    app.context.showView('overview');
  }
  assert.equal(app.focused.length, 5);
  assert.ok(app.focused.every(f => !f.hidden));
});

test('external entry also refreshes when data arrives after the initial reveal', () => {
  const app = lifecycle();
  app.context.window.location.search = '?view=radar';
  app.context.openLinkedView();
  app.frame();
  app.frame();
  assert.equal(app.focused.length, 0);
  app.load();
  app.frame();
  app.frame();
  assert.deepEqual(app.focused, [{ id: 'e001', presentationReady: true, hidden: false }]);
});

test('selection measures the completed Radar layout before focusing, without waiting for observers', () => {
  const source = read('radar.js');
  let top = 280;
  let height;
  let cachedHeight;
  let visible = true;
  const focusSizes = [];
  const context = vm.createContext({
    document: {
      body: { classList: { contains: () => visible } },
      getElementById: () => ({}),
    },
    window: { innerHeight: 800, dispatchEvent() {} },
    CustomEvent: class {},
    workspace: {
      getBoundingClientRect: () => ({ top }),
      style: { setProperty(name, value) { assert.equal(name, '--radar-available-height'); height = value; } },
    },
    map: { invalidateSize() { cachedHeight = height; } },
    selectMatch() { focusSizes.push(cachedHeight); },
    updateSidebarView() {}, highlight() {},
    list: { querySelectorAll: () => [] },
    currentDataset: 'estimated', analysis: { matches: [] },
  });
  vm.runInContext(source.slice(source.indexOf('  let fitFrame;'), source.indexOf("  window.addEventListener('resize'")), context);
  vm.runInContext(source.slice(source.indexOf('  const originalSelect = selectMatch;'), source.indexOf('  const originalRender = render;')), context);
  context.selectMatch('e001');
  assert.deepEqual(focusSizes, ['504px']);
  top = 340; // Wrapped controls or changed metrics on re-entry.
  context.selectMatch('e002');
  assert.deepEqual(focusSizes, ['504px', '444px']);
  visible = false;
  top = 0;
  context.sizeRadarViewport();
  assert.equal(height, '444px', 'hidden layout must not replace the visible measurement');
});
