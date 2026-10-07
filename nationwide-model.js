(function (root) {
  "use strict";
  const esc = (value) =>
    String(value ?? "").replace(
      /[&<>"']/g,
      (c) =>
        ({
          "&": "&amp;",
          "<": "&lt;",
          ">": "&gt;",
          '"': "&quot;",
          "'": "&#39;",
        })[c],
    );
  const safeUrl = (value) => {
    try {
      const u = new URL(value);
      return ["https:", "http:"].includes(u.protocol) &&
        !u.username &&
        !u.password
        ? u.href
        : null;
    } catch {
      return null;
    }
  };
  const dateLabel = (value) =>
    !value?.value ? "Unknown" : `${value.value} · ${value.precision} precision`;
  const confidenceLabel = (value) =>
    ({
      verified: "Reviewed location",
      official: "Official coordinates",
      tentative: "Tentative location",
      unresolved: "Unlocated",
    })[value] || "Unknown";
  function viewport(bounds) {
    const width = bounds.east - bounds.west;
    const wrap = (v) => ((((v + 180) % 360) + 360) % 360) - 180;
    return [
      width >= 360 ? -180 : wrap(bounds.west),
      Math.max(-90, bounds.south),
      width >= 360 ? 180 : wrap(bounds.east),
      Math.min(90, bounds.north),
    ]
      .map((v) => Number(v.toFixed(5)))
      .join(",");
  }
  function csv(records) {
    const cell = (v) => {
      let s = String(v ?? "");
      if (/^[=+\-@\t\r]/.test(s)) s = "'" + s;
      return '"' + s.replace(/"/g, '""') + '"';
    };
    return [
      [
        "id",
        "name",
        "owner",
        "states",
        "status",
        "confidence",
        "in_service",
        "date_precision",
        "source_url",
      ],
      ...records.map((r) => [
        r.id,
        r.name,
        r.owner,
        r.states.join(";"),
        r.status,
        r.confidence,
        r.milestone.value,
        r.milestone.precision,
        r.provenance.source_url,
      ]),
    ]
      .map((r) => r.map(cell).join(","))
      .join("\r\n");
  }
  function activeAlerts(feed, now = Date.now()) {
    return {
      ...feed,
      records: (feed.records || []).filter(
        (r) =>
          Number.isFinite(Date.parse(r.expires)) && Date.parse(r.expires) > now,
      ),
    };
  }
  const api = {
    esc,
    safeUrl,
    dateLabel,
    confidenceLabel,
    viewport,
    csv,
    activeAlerts,
  };
  if (typeof module !== "undefined" && module.exports) module.exports = api;
  root.NationModel = api;
})(typeof window === "undefined" ? globalThis : window);
