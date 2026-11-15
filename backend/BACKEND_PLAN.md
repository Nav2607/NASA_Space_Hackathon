# Backend Plan: Agronaut

Goal: given a location and farmer inputs, return a baseline evaluation plus 3-5 alternative crop rotations, each with scores, ratings, confidence labels and plain-language explanations.

Scientific correction supersedes the independent crop-year lookup approach below:
the current engine runs continuous chronological rotations with all starting
phases, fixed bucket capacity and common initialization. Cover variants are
excluded until defensible demand inputs exist; constraints are never relaxed to
reach three options. Historical periods are 2005–2014 and 2015–2024, and the future
target is 2031–2050 with independently simulated NEX models and Hargreaves in all
runs. Legacy processed datasets remain preserved but are not used for scoring.
See [SCIENTIFIC_VALIDITY.md](SCIENTIFIC_VALIDITY.md) for current API changes,
methods and limitations; the older build plan below is retained as historical
planning context where it conflicts with that correction.

## 1. Architecture (the key decision)

**Python does everything. The frontend only displays.**

```
 OFFLINE (run once, results committed)             RUNTIME (fast, no external calls)
 ---------------------------------------           ----------------------------------
 NASA POWER  -> data/raw/power/<anchor>.csv        FastAPI app
 SMAP (post-MVP; origin/smap 2e03043)               |- loads reference JSON + precomputed tables
 NEX (opt.)  -> data/raw/nex/<anchor>.csv            |- generates / filters / scores rotations
                    |                                |- returns JSON (the frontend contract)
                    v
 Reference tables (hand-cited JSON): crops, soils, rotation rules
                    |
                    v
 PRECOMPUTE: simulate every crop x soil x anchor x weather-year
          -> data/processed/crop_year_metrics.parquet   (small, a few thousand rows)
```

Why precompute: a rotation is just a sequence of crops, so once each (anchor, soil, crop, weather year) is simulated, evaluating any rotation is a lookup and an average. The API then answers in milliseconds, and the same tables can be exported as static JSON if you want to host without a server.

Stack: Python 3.11+, pandas, numpy, FastAPI, pydantic, pytest. Add earthaccess/xarray only if SMAP or NEX is used.

## 2. Folder structure

```
backend/
  data/
    anchors.json                  (exists)
    reference/                    hand-entered, cited
      crops.json
      soil_texture.json
      rotation_rules.json
    raw/power/<anchor>.csv        (move the existing weather.csv here, or keep path)
    processed/
      crop_year_metrics.parquet
      anchor_summary.json         per-anchor stats for the map (dry-year shortfall, heat days)
  data_scripts/
    fetch_power.py                (exists; extend, see step 1)
    fetch_smap.py                 post-MVP; preserved on origin/smap, not this branch
    fetch_nex.py                  optional
    build_metrics.py              runs the engine over all combos
  engine/
    et0.py                        Penman-Monteith (Hargreaves fallback)
    water_balance.py              soil-water bucket
    stress.py                     heat/dry days, wet-spring indicator
    ratings.py                    nitrogen, soil cover, pest-break, residue
    rotations.py                  generate + rules filter
    scoring.py                    normalize, weight, label options
    explain.py                    template-based "why / trade-offs"
    confidence.py                 per-metric confidence labels
  api/
    main.py                       FastAPI app
    schemas.py                    pydantic request/response models
  tests/
  BACKEND_PLAN.md
```

## 3. Build order (each step ends with something testable)

| # | Step | Output | Est. |
|---|------|--------|------|
| 1 | **Data pull.** Fix units bug in `fetch_power.py`, set START to 1981, run all 12 anchors, validate (row counts, gaps, sanity ranges). SMAP is deferred; do not submit additional requests. | 12 CSVs | 1-2 h |
| 2 | **Reference tables.** Fill `crops.json`, `soil_texture.json`, `rotation_rules.json` from FAO-56 and OMAFRA with a `sources` field on every value. Unknown = `null`. Add a schema validator that fails on any number without a source. | 3 JSON files | 2-3 h |
| 3 | **ET0 and crop water use.** Penman-Monteith from POWER fields (Tmax, Tmin, RH, wind, solar), Hargreaves fallback. ETc = Kc(stage) x ET0. Unit-test against a hand-worked FAO-56 example. | `et0.py` | 2 h |
| 4 | **Soil-water bucket.** Daily store, stress days, shortfall (mm). Run the full year, carrying water between seasons, so cover crops are not penalized unfairly. | `water_balance.py` | 2 h |
| 5 | **Stress and risk metrics.** Heat days in the critical window, dry days, heavy-rain days (>25 mm) on bare soil in Apr-May. | `stress.py` | 1 h |
| 6 | **Ratings (rule-based).** Nitrogen demand with legume credit, soil cover fraction, pest-break rating, residue class. | `ratings.py` | 2 h |
| 7 | **Precompute.** For every anchor x soil x crop x year, store seasonal ETc, shortfall, stress days. Compute typical (median) and dry (90th percentile) summaries. | parquet | 1-2 h |
| 8 | **Rotation engine.** Enumerate 2-4 year sequences, apply rules (min gaps, predecessors), apply constraints (must, avoid, equipment), evaluate by lookup, score against the baseline, weight by sliders, label options. | `rotations.py`, `scoring.py` | 3-4 h |
| 9 | **Explanations and confidence.** Templates for "why / trade-offs" and per-metric confidence from `data_quality`. | `explain.py`, `confidence.py` | 1-2 h |
| 10 | **API.** Wire it up with FastAPI and CORS, plus the endpoints below. | running server | 2 h |
| 11 | **Validation extras.** Anchor summary for the map, optional NEX delta method. SMAP observational cross-check is post-MVP only. | see section 7 | 2-4 h |

Steps 1-2 can run in parallel. Steps 3-6 depend on 1-2. Total about 18-24 h of backend work, so confirm the cut order in section 7.

## 3b. Division of work

If two people split this, one takes data and reference tables (steps 1, 2, 11) and the other takes engine and API (steps 3-10). Agree the JSON shapes in section 4 first.

## 4. API contract (agree on this with the frontend before building)

All endpoints are GET or POST with JSON.

| Endpoint | Purpose |
|----------|---------|
| `GET /anchors` | The 12 anchors plus summary stats for the map |
| `GET /snap?lat=&lon=` | Nearest anchor, with distance in km (reject points outside Southern Ontario) |
| `GET /reference` | Crops, soil textures and rotation rules, so dropdowns are built from the same source of truth |
| `POST /baseline` | Evaluate the farmer's current rotation |
| `POST /recommend` | Baseline plus 3-5 labelled alternatives |
| `GET /evidence` | Data sources, resolutions, date ranges, limitations text |

`POST /recommend` request:
```json
{
  "lat": 43.55, "lon": -80.25,
  "soil": "loam", "tile_drainage": true, "irrigation": false,
  "equipment": ["planter", "combine"],
  "current_rotation": ["corn", "soybean"],
  "must_include": ["corn"], "avoid": [],
  "priorities": {"water": 0.4, "nitrogen": 0.3, "soil_cover": 0.2, "weather_risk": 0.1}
}
```

Response (shape, not final values):
```json
{
  "anchor": {"id": "guelph", "distance_km": 12.3},
  "baseline": {"rotation": ["corn","soybean"], "metrics": {...}, "confidence": {...}},
  "options": [
    {"label": "lowest_water", "rotation": [...], "vs_baseline_pct": {"water_use": 85, ...},
     "metrics": {...}, "why": "...", "tradeoffs": [...], "confidence": {...}, "warnings": []}
  ],
  "charts": {"typical_vs_dry": {...}, "monthly_soil_water": {...}},
  "sources": {"water_use": "Simulated", "nitrogen": "Rule-based", "weather": "NASA-derived"}
}
```

Every metric carries a source tag and a confidence label. Percentages are rounded to the nearest 5%. A `warnings` list carries messages like "no irrigation and large dry-year shortfall" or "missing data for crop X".

## 5. Data design rules

- Every number in the reference tables has a source, or it is `null`. `null` surfaces as "no data" and lowers confidence.
- Weather years are never mixed arbitrarily: each crop is simulated against each historical year, then summarized as median (typical) and 90th percentile (dry).
- Planting dates come from each crop's default window. Rotation workload overlap comes from the same calendars.
- Keep raw, processed and reference data in separate folders. Raw and processed outputs are reproducible from scripts.
- Snap each click to the nearest anchor and return the distance, so the frontend can show which point was used.

## 6. Testing

- **Unit tests:** ET0 against a published FAO-56 worked example, bucket logic on a toy 10-day series, and nitrogen rating on a few known rotations.
- **Rule tests:** corn-corn must be flagged, a must-include crop must appear in every option, and an avoided crop must never appear.
- **Sanity checks:** seasonal ETc for corn in Ontario should be roughly 450-600 mm, and the dry-year shortfall must be at least the typical-year shortfall.
- **API tests:** schema validation and a full request/response for 2-3 sample farms. Save them as fixtures the frontend can use as mock data.

## 7. Optional work and cut order

1. **SMAP observational cross-check — deferred post-MVP.** The extraction pipeline, tests, documentation and Guelph pilot cache (2016-01-01) are preserved on `origin/smap`, commit `2e03043`, separately from core backend development. Existing local intermediate samples remain intact and ignored. Do not initiate additional SMAP downloads or integrate SMAP into the simulation or recommendation engine. Future regional comparisons require separate scoping and must not be described as farm-level validation. See [SMAP_SETUP.md on the preserved commit](https://github.com/Nav2607/NASA_Space_Hackathon/tree/2e03043/backend/SMAP_SETUP.md) for retained technical details.
2. **NEX-GDDP-CMIP6 "2050s".** Use the delta method: compute monthly temperature and precipitation changes from 3+ models, apply them to the historical POWER series, and rerun the engine.
3. **Anchor summary for the map.** Cheap and valuable; do it before SMAP or NEX.
4. **AAFC soil layer.** Only if a downloadable licensed dataset is found quickly.

SMAP is already deferred beyond the MVP. For the remaining optional work, cut order if behind: NEX, then AAFC. Keep the anchor summary.

## 8. Open decisions to settle first

1. **Server or static?** FastAPI is recommended. If you need free static hosting for the demo, export the precomputed tables and the rotation logic to JSON, and port the rotation step to JavaScript later.
2. **Crop list.** Start with corn, soybean, winter wheat, red clover and cereal rye. Add others (oats, canola, forages) only if reference data is available. Rice-style "hard constraint, low data" cases are handled by the `null` and confidence mechanism.
3. **Soil-health scope.** Decide whether pest-break and residue ratings are in. I recommend yes, because the challenge names them explicitly.
4. **Weather-year handling.** Use all 40+ years (1981-2024) for trends, and the most recent 20 for typical and dry-year statistics.
   **Decided:** POWER solar radiation is missing for the first ~1,100 days at every anchor (1981 until 1988-1999, depending on location), plus ~190 scattered days after mid-1983. The water model (Penman-Monteith) runs only on years with complete data, so solar values are never estimated or filled. Temperature and rainfall trends use the full 1981-2024 record. Step 1's validation should list the usable years per anchor.
