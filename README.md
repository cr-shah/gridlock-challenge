# Gridlock Challenge — starter kit

Static pipeline, no backend: `projects.json` → `scoring_engine.py` → `analysis.json` → `index.html`.

## Run it

```bash
pip install pandas shapely
python scoring_engine.py            # reads data/projects.json, writes data/analysis.json
python -m http.server 8000          # serve the folder — do NOT just double-click index.html
```
Then open `http://localhost:8000`. Opening the HTML file directly (`file://`) will fail silently on the `fetch()` call in most browsers — that's the #1 time-waster on demo day, so build the habit of running the local server now.

A working `data/analysis.json` is already included (built from the placeholder seed data below), so the frontend renders immediately even before you touch the Python.

## Data schema

**Input — `data/projects.json`**
```json
{
  "projects": [
    {
      "id": "desc-002",
      "utility": "DESC",
      "name": "Okatie - McIntosh 115kV Tie Reactor",
      "lat1": 32.26, "lng1": -80.87,
      "lat2": 32.15, "lng2": -81.24,
      "start_year": 2027, "end_year": 2027,
      "source_url": "https://..."
    }
  ]
}
```
- Point projects (a substation upgrade, not a line) just repeat `lat1/lng1` as `lat2/lng2` — the engine treats every project as a line segment uniformly, so you never need a branch for "is this a point or a line."
- `source_url` isn't used by the math, but keep it on every real entry — you'll want it live during Q&A when a judge asks "where did this come from."

**Output — `data/analysis.json`** (one entry per flagged match, already sorted best-first)
```json
{
  "utilities": ["DESC", "GPC"],
  "matches": [
    {
      "match_id": "m001",
      "project_a": { "...full project object..." },
      "project_b": { "...full project object..." },
      "distance_km": 0.0,
      "tier": "touching_crossing",
      "timeline_overlap": true,
      "overlap_years": [2027, 2027],
      "closest_point_a": { "lat": 32.15, "lng": -81.24 },
      "closest_point_b": { "lat": 32.15, "lng": -81.24 },
      "score": 115,
      "coordination_brief": "...",
      "est_savings_usd": { "low_usd": 250000, "high_usd": 600000, "assumption": "Illustrative..." }
    }
  ]
}
```

## The seed data is placeholder — read this before demo day

`data/projects.json` uses **approximate** town/plant coordinates (Okatie, Bluffton, Urquhart, Martinez, Plant McIntosh, Thomson–Vogtle) so the pipeline runs end-to-end right now. Before you submit, swap in real coordinates pulled from the SCRTP document-library PDFs and the SERTP regional transmission plan — geocode substation/line names with OpenStreetMap's Nominatim (free, no key). Don't present placeholder coordinates as verified in your pitch.

## What the scoring engine actually does

1. Converts every project's lat/lng into a local flat plane in kilometers (equirectangular projection, centered on each pair's own mean latitude) — validated against haversine at <0.01% error for this region.
2. Builds a `shapely` `LineString` for each project (a point project becomes a zero-length line) and calls `.distance()` between every cross-utility pair — this is the **true closest-point distance**, not centroid-to-centroid, which is exactly what the challenge doc calls out as the thing most teams will get wrong.
3. Buckets the result into the four challenge tiers, checks whether build years overlap, and scores/ranks (tier weight + a timeline-overlap bonus).
4. Also returns the two actual closest points (via `nearest_points`) so the frontend can draw the real connecting segment on the map instead of a line between arbitrary centroids — a small detail that visibly proves you did the geometry right.
5. Every dollar figure is generated from a clearly-labeled illustrative range per tier — never presented as a real number.

## Team split (parallel, not sequential)

- **Data**: curate ~15-20 real projects from the SCRTP/SERTP PDFs, geocode with Nominatim, fill `projects.json`.
- **Scoring**: already done above — mostly your job is validating it against real data and tuning the savings-range assumptions.
- **Frontend**: already scaffolded — your job is polish, the detail panel, and wiring up new tiers/utilities if you add a third one.

Agree on the JSON schema above before splitting up — that's what lets all three of you work in parallel without blocking each other.

---

## The 3-minute pitch

**0:00–0:30 — The hook (real, not hypothetical)**
"FERC issued Order 1920 in 2024 specifically because utilities plan construction in isolation — no visibility into what the neighboring utility is doing a few miles away. DESC and Georgia Power already sit in the same regional coordination forum, SERTP, but don't compare project-level plans at this granularity. We built the tool that does."

**0:30–1:30 — Live demo**
Open the map already zoomed to the Savannah/Augusta border. Move the year slider — watch matches fade in and out as build windows shift. Click the top-ranked match (ideally your touching/crossing pair). Show the sidebar's ranked list and the generated coordination brief. Point out the one dashed, muted-colored line — "same location, different years — this is the other failure mode: two utilities building in the same spot but far enough apart in time that nobody notices the missed opportunity to sequence them together."

**1:30–2:15 — The methodology (this is where you separate from other teams)**
"We measure closest-point distance, not centroid distance — a 60km line can pass 5km from another substation, and the challenge brief specifically warns that centroid math misses that. We project coordinates into a local flat plane before measuring, validated against the haversine formula to under a hundredth of a percent, then bucket into the exact four tiers in the brief: touching/crossing, 1.6km, 8km, 40km." (Show the connecting line snapping to the true closest points on two of your line-shaped projects — visual proof, not just a claim.)

**2:15–2:45 — The savings estimate, framed honestly**
"For the top match we generate an illustrative savings range, clearly labeled as an assumption about avoided duplicate mobilization cost — not a claimed real utility figure. We'd rather be honest about what's an estimate than pretend precision we don't have."

**2:45–3:00 — Close**
"With more time: real geocoded data across all of SERTP's balancing authorities — Duke, TVA, LG&E/KU, Southern — not just this one pair, since our matching engine already generalizes to any number of utilities, not just two. This is a hackathon-scale version of a coordination gap that's costing the industry real money right now."
