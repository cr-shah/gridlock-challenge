(function (root) {
  "use strict";
  const DAY = 86400000;
  // Precision describes an interval, not a guessed construction window.
  function interval(value, precision) {
    const patterns = {
      year: /^\d{4}$/,
      month: /^\d{4}-\d{2}$/,
      day: /^\d{4}-\d{2}-\d{2}$/,
    };
    if (typeof value !== "string" || !patterns[precision]?.test(value))
      return null;
    const [year, month = 1, day = 1] = value.split("-").map(Number);
    if (
      !Number.isInteger(year) ||
      year < 1900 ||
      year > 2200 ||
      month < 1 ||
      month > 12 ||
      day < 1 ||
      day > 31
    )
      return null;
    const start = Date.UTC(year, month - 1, day);
    if (
      new Date(start).getUTCMonth() !== month - 1 ||
      new Date(start).getUTCDate() !== day
    )
      return null;
    const end =
      precision === "year"
        ? Date.UTC(year + 1, 0, 1)
        : precision === "month"
          ? Date.UTC(year, month, 1)
          : start + DAY;
    return { start, end, year, precision };
  }
  function compare(a, b) {
    const x = interval(a?.value, a?.precision),
      y = interval(b?.value, b?.precision);
    if (!x || !y) return null;
    // Last included day matters: a day-precision interval has exactly one possible date.
    const lastX = x.end - DAY,
      lastY = y.end - DAY;
    const min = Math.max(0, y.start - lastX, x.start - lastY) / DAY;
    const max =
      Math.max(Math.abs(x.start - lastY), Math.abs(lastX - y.start)) / DAY;
    return { min, max, overlaps: min === 0 };
  }
  function replay(history, rules) {
    const n = Number(rules.workdays),
      rain = Number(rules.rain);
    if (
      !Number.isInteger(n) ||
      n < 1 ||
      n > 60 ||
      !Number.isFinite(rain) ||
      rain <= 0 ||
      rain > 10
    )
      throw new Error(
        "Choose 1–60 workdays and a rain threshold greater than 0, up to 10 inches.",
      );
    const checks = [["prcp_in", rain, "rain", false]];
    for (const [field, key, low, min, max] of [
      ["wsf2_mph", "wind", false, 1, 200],
      ["tmax_f", "heat", false, 32, 150],
      ["tmin_f", "freeze", true, -80, 60],
    ]) {
      if (rules[key] !== null && rules[key] !== undefined) {
        const v = Number(rules[key]);
        if (!Number.isFinite(v) || v < min || v > max)
          throw new Error(
            "Weather thresholds are outside the supported range.",
          );
        checks.push([field, v, key, low]);
      }
    }
    const start = Date.parse(history.window.start + "T00:00:00Z"),
      end = Date.parse(history.window.end + "T00:00:00Z");
    if (
      !Number.isFinite(start) ||
      !Number.isFinite(end) ||
      end < start ||
      end - start > 20 * 366 * DAY
    )
      throw new Error("Invalid observation window.");
    const first = new Date(start).getUTCFullYear(),
      last = new Date(end).getUTCFullYear();
    const output = [];
    for (let month = 0; month < 12; month++) {
      const trials = [],
        excluded = { missing: 0, window: 0, horizon: 0 };
      for (let year = first; year <= last; year++) {
        const begin = Date.UTC(year, month, 1);
        let complete = 0,
          elapsed = 0,
          baseline = 0,
          baselineDone = 0,
          failure = null;
        const stopped = { rain: 0, wind: 0, heat: 0, freeze: 0 };
        while (baselineDone < n) {
          const d = new Date(begin + baseline * DAY).getUTCDay();
          baseline++;
          if (d !== 0 && d !== 6) baselineDone++;
        }
        while (complete < n && elapsed < 180) {
          const time = begin + elapsed * DAY,
            d = new Date(time).getUTCDay();
          elapsed++;
          if (time < start || time > end) {
            failure = "window";
            break;
          }
          if (d === 0 || d === 6) continue;
          const i = Math.round((time - start) / DAY);
          let missing = false;
          const reasons = [];
          for (const [field, threshold, label, low] of checks) {
            const v = history.observations[field]?.[i];
            if (v === null || v === undefined || !Number.isFinite(v))
              missing = true;
            else if (low ? v <= threshold : v >= threshold) reasons.push(label);
          }
          if (reasons.length) for (const reason of reasons) stopped[reason]++;
          else if (missing) {
            failure = "missing";
            break;
          } else complete++;
        }
        if (complete < n) excluded[failure || "horizon"]++;
        else trials.push({ year, elapsed, extra: elapsed - baseline, stopped });
      }
      const sorted = trials.map((t) => t.extra).sort((a, b) => a - b);
      const mid = Math.floor(sorted.length / 2);
      output.push({
        month: month + 1,
        trials,
        excluded,
        attempted: last - first + 1,
        median: sorted.length
          ? (sorted[(sorted.length - 1) >> 1] + sorted[mid]) / 2
          : null,
        min: sorted.length ? sorted[0] : null,
        max: sorted.length ? sorted[sorted.length - 1] : null,
      });
    }
    return output;
  }
  const api = { interval, compare, replay };
  if (typeof module !== "undefined" && module.exports) module.exports = api;
  root.PlanningModel = api;
})(typeof window === "undefined" ? globalThis : window);
