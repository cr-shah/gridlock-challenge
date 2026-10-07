const test = require("node:test");
const assert = require("node:assert/strict");
const M = require("../nationwide-model.js");
test("source content cannot inject HTML or unsafe links", () => {
  assert.equal(M.esc('<img onerror="x">'), "&lt;img onerror=&quot;x&quot;&gt;");
  assert.equal(M.safeUrl("javascript:alert(1)"), null);
  assert.equal(M.safeUrl("https://user:secret@example.com"), null);
});
test("unknown dates and tentative locations retain their meaning", () => {
  assert.equal(M.dateLabel({ value: null, precision: "unknown" }), "Unknown");
  assert.equal(
    M.dateLabel({ value: "2030", precision: "year" }),
    "2030 · year precision",
  );
  assert.equal(M.confidenceLabel("tentative"), "Tentative location");
});
test("viewport wraps Alaska across the antimeridian without reversing latitude", () => {
  assert.equal(
    M.viewport({ west: 170, south: 50, east: 230, north: 72 }),
    "170,50,-130,72",
  );
  assert.equal(
    M.viewport({ west: -200, south: -85, east: 200, north: 85 }),
    "-180,-85,180,85",
  );
});
test("CSV escapes spreadsheet formula injection and retains evidence", () => {
  const csv = M.csv([
    {
      id: "x",
      name: '=HYPERLINK("bad")',
      owner: "ACME",
      states: ["13"],
      status: "unknown",
      confidence: "tentative",
      milestone: { value: null, precision: "unknown" },
      provenance: { source_url: "https://example.com" },
    },
  ]);
  assert.ok(csv.includes('"\'=HYPERLINK(""bad"")"'));
  assert.ok(csv.includes("https://example.com"));
});
test("cached alerts discard expired and malformed expirations without mutating the feed", () => {
  const M = require("../nationwide-model.js");
  const feed = {
    records: [
      { id: "expired", expires: "2026-10-07T00:00:00Z" },
      { id: "active", expires: "2026-10-08T00:00:00Z" },
      { id: "bad", expires: null },
    ],
  };
  assert.deepEqual(
    M.activeAlerts(feed, Date.parse("2026-10-07T12:00:00Z")).records.map(
      (r) => r.id,
    ),
    ["active"],
  );
  assert.equal(feed.records.length, 3);
});
