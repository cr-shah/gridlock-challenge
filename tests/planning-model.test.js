const test = require("node:test");
const assert = require("node:assert/strict");
const { interval, compare, replay } = require("../planning-model.js");
function history() {
  return {
    window: { start: "2020-01-01", end: "2020-12-31" },
    observations: {
      prcp_in: Array(366).fill(0),
      wsf2_mph: Array(366).fill(0),
      tmax_f: Array(366).fill(70),
      tmin_f: Array(366).fill(40),
    },
  };
}
test("precision intervals include leap days and reject invalid or unknown dates", () => {
  assert.equal(
    (interval("2020", "year").end - interval("2020", "year").start) / 86400000,
    366,
  );
  assert.equal(
    (interval("2020-02", "month").end - interval("2020-02", "month").start) /
      86400000,
    29,
  );
  assert.equal(interval("2021-02-29", "day"), null);
  assert.equal(interval("3033", "year"), null);
  assert.equal(interval(null, "unknown"), null);
  assert.equal(interval("2020", "day"), null);
  assert.equal(interval("2020-02", "year"), null);
});
test("interval gaps do not pretend year precision is exact", () => {
  assert.deepEqual(
    compare(
      { value: "2020", precision: "year" },
      { value: "2021", precision: "year" },
    ),
    { min: 1, max: 730, overlaps: false },
  );
  assert.deepEqual(
    compare(
      { value: "2020-02-29", precision: "day" },
      { value: "2020-03-01", precision: "day" },
    ),
    { min: 1, max: 1, overlaps: false },
  );
  assert.equal(
    compare(
      { value: "2020", precision: "year" },
      { value: "2020-04", precision: "month" },
    ).overlaps,
    true,
  );
});
test("dry weekdays reproduce baseline; weekends never count as work", () => {
  const r = replay(history(), { workdays: 3, rain: 0.5 });
  assert.equal(r[0].median, 0);
  assert.equal(r[0].trials[0].elapsed, 3);
  assert.equal(r[1].trials[0].elapsed, 5); // Feb 1 2020 is Saturday
});
test("rain threshold inclusive and delay includes the shifted weekend", () => {
  const h = history();
  h.observations.prcp_in[0] = 0.5;
  const r = replay(h, { workdays: 3, rain: 0.5 })[0];
  assert.equal(r.median, 3);
  assert.equal(r.trials[0].stopped.rain, 1);
});
test("missing eligible workday excludes trial, never assumes dry", () => {
  const h = history();
  h.observations.prcp_in[0] = null;
  const r = replay(h, { workdays: 3, rain: 0.5 })[0];
  assert.equal(r.median, null);
  assert.equal(r.excluded.missing, 1);
});
test("known stop is sufficient even if a different variable is missing", () => {
  const h = history();
  h.observations.prcp_in[0] = 1;
  h.observations.wsf2_mph[0] = null;
  assert.equal(replay(h, { workdays: 3, rain: 0.5, wind: 28 })[0].median, 3);
});
test("missing optional wind does not affect rain-only replay", () => {
  const h = history();
  h.observations.wsf2_mph = null;
  assert.equal(replay(h, { workdays: 3, rain: 0.5 })[0].median, 0);
  assert.equal(
    replay(h, { workdays: 3, rain: 0.5, wind: 28 })[0].excluded.missing,
    1,
  );
});
test("archive cutoff and pathological continuous stops are excluded", () => {
  const h = history();
  assert.equal(replay(h, { workdays: 60, rain: 0.5 })[11].excluded.window, 1);
  h.observations.prcp_in.fill(1);
  assert.equal(replay(h, { workdays: 20, rain: 0.5 })[0].excluded.horizon, 1);
});
test("invalid scenario values are refused", () => {
  for (const workdays of [0, 61, 2.5, NaN])
    assert.throws(() => replay(history(), { workdays, rain: 0.5 }));
  assert.throws(() => replay(history(), { workdays: 20, rain: 0 }));
  assert.throws(() =>
    replay(history(), { workdays: 20, rain: 0.5, wind: 999 }),
  );
});
