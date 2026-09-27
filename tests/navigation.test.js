'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');

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
  const radarScript = html.indexOf('<script src="radar.js"></script>');
  const initialReveal = html.indexOf('<script>openLinkedView();</script>');
  assert.ok(radarScript >= 0 && initialReveal > radarScript);
  assert.equal((html.match(/openLinkedView\(\);/g) || []).length, 1);
});
