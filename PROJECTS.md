# Agronaut — Project specification (v5)

NASA Space Apps 2026 · Field Shift: Adapting Farms with NASA Data

## 1. Pitch

**Is your crop rotation ready for tomorrow's climate?** Simulate Southern Ontario crop rotations using 20 years of NASA-derived historical weather and 2031–2050 climate projections, identify vulnerabilities, and compare feasible adaptations. Decision support, not a single best rotation.

Example: a corn–soybean farmer must retain corn, has no irrigation and wants less fertilizer dependence. Compare their baseline with feasible alternatives under historical and projected conditions.

## 2. Questions

1. What environmental vulnerabilities exist in my current rotation?
2. How might they change under future climate?
3. Which feasible adjustments improve resilience?

## 3. Scope

- Southern Ontario: 6–8 representative anchors; snap to nearest supported anchor and display location and resolution.
- Cash crops: corn, soybean, winter wheat. Cover crops: underseeded red clover, cereal rye.
- Historical 2005–2024, split 2005–14 and 2015–24; future 2031–2050.
- SSP2-4.5 required if accessible; SSP3-7.0 optional. Target 2–3 independently simulated models.
- One location per session. No accounts, yield, profit or live forecasts.
- Footer: “Decision support, not agronomic advice.” Concise metric tooltips and collapsed evidence panel.

## 4. Data

| Dataset | Role | Priority |
|---|---|---|
| NASA POWER daily, 2005–2024 | Atmospheric conditions, ET0, crop demand, heat stress | P0 |
| GPM IMERG Final, ~0.1°, 2005–2024 | Precipitation, heavy rainfall, dry spells | P0 |
| NEX-GDDP-CMIP6, ~0.25° | Future temperature and precipitation; POWER projection API if available | P0 |
| MODIS MOD13Q1 NDVI/EVI | Historical vegetation anomaly observational comparison | P1 |
| SMAP L4 | Optional post-MVP regional observational cross-check | Post-MVP (deferred) |

- POWER precipitation is the fallback, never added to GPM.
- SMAP is deferred beyond the MVP. Its extraction pipeline, tests, documentation and retrieved Guelph pilot (2016-01-01) are preserved on `origin/smap`, commit [`2e03043`](https://github.com/Nav2607/NASA_Space_Hackathon/tree/2e03043), for future use; these files are not part of the backend branch. Do not initiate additional SMAP downloads or integrate SMAP into the simulation or recommendation engine. Any future cross-check is regional context, not farm-level validation; volumetric moisture must not be used directly as bucket storage or initialization.
- Run models independently; report median and range of outcomes, not averaged daily weather.
- Where feasible, extract a reference period from each NEX model to distinguish projected changes from cross-product differences; otherwise disclose this limitation.
- Historical decade differences do not prove a long-term climate trend. Future sequences are scenarios, not exact daily forecasts.
- Preprocess offline in Python; cache per anchor. No live NASA calls during the demo.
- Preserve dates, units, product versions, resolutions, coordinates, model/scenario IDs and missing data metadata.
- Test projection extraction within the first 30 minutes; use the labeled sensitivity fallback if blocked.
- Agricultural references: FAO-56 (Kc, stages, root depth), Ontario agricultural extension/University of Guelph (calendars, rotation rules, N guidance), cited soil plant-available water per metre. Do not invent parameters.

Sources: [POWER](https://power.larc.nasa.gov/), [POWER projection API](https://power.larc.nasa.gov/docs/services/api/projection/), [GPM](https://gpm.nasa.gov/data/imerg), [SMAP](https://smap.jpl.nasa.gov/data/), [FAO-56](https://www.fao.org/4/X0490E/X0490E00.htm). Verify product access and versions during implementation.

## 5. Farmer inputs

Location, soil texture, existing rotation, irrigation (context only), equipment, must-grow/avoid crops, willingness to add cover crops, priority sliders (water, weather resilience, soil protection, nitrogen). Retain baseline even if it conflicts with new constraints. All simulations are rainfed unless irrigation is explicitly modeled.

## 6. Scientific engine

1. **ET0:** Hargreaves (FAO-56), correct extraterrestrial radiation units, nonnegative. Penman–Monteith only if all inputs are consistently available for historical and future conditions.
2. **Crop demand:** ETc = Kc × ET0. Document combined Kc approximation for overlapping cover and cash crops; no double counting.
3. **Continuous water bucket:** C = plant-available water per metre × fixed representative soil depth. Daily quantities in mm:

   ```text
   A = S + P
   ETa = min(ETc, A)
   U = ETc - ETa
   D = max(0, A - ETa - C)
   S_next = A - ETa - D
   ```

   S is available storage, P precipitation entering bucket, U unmet demand, D excess water. Preserve mass balance and storage across seasons and years. Winter wheat spans calendar years. Document initialization, offseason evaporation and winter precipitation assumptions. Simplifies declining uptake before depletion.
4. **Stress:** heat and threshold-based water stress during sensitive stages (cited thresholds). Water stress days are distinct from unmet demand.
5. **Soil protection:** daily protective-cover fraction from calendars and residue assumptions. E = sum(P × (1 − cover)) during documented non-frozen season. Count heavy-rain days on low cover using documented thresholds. Exposure proxy, not predicted erosion.
6. **Nitrogen:** qualitative 1–3 rating (corn high, wheat medium, soybean low external fertilizer demand). Apply documented credits only.
7. **Fair comparison:** common climate periods, consistent initialization, annualized metrics, median and 90th-percentile shortfall. Evaluate all rotation starting phases. Reduce candidate count before sacrificing fairness.

Unknown parameters remain `null`, never zero. Missing essentials return insufficient data. Lower actual water consumption due to stress is not an improvement.

## 7. Features

- **Climate Blind Spots (hero):** year-long crop stages, protective cover and sensitive windows overlaid with precipitation and heat/water stress. Explain important overlaps and potential adaptations.
- **Climate Time Machine:** compare 2005–14, 2015–24 and 2031–2050 for demand, shortfall, heat stress and exposure; show projected model range.
- **Climate-resilient adaptations:** compare historical and projected performance, model-run agreement and trade-offs.
- **Adverse-year replay (P1):** replay a real adverse historical year (e.g. 2012) only where local data supports selection.
- **Satellite observational check (P1):** quality-filtered MODIS vegetation anomalies for comparable agricultural areas and growth periods versus historical modeled regional stress. Not validation of hypothetical rotations.

## 8. Recommendations

1. Evaluate existing rotation (default corn–soybean, labeled).
2. Generate 2–4 year cash-crop sequences plus compatible cover variants.
3. Filter must-grow, avoid, equipment and agronomic compatibility.
4. Normalize metrics within each category then apply farmer weights. Future scoring uses model-median outcomes.

| Priority | Metrics |
|---|---|
| Water | Potential demand, shortfall |
| Weather resilience | Sensitive-stage heat and water stress |
| Soil protection | Protective cover, rainfall exposure |
| Nitrogen | Qualitative nitrogen rating |

5. Optionally remove dominated options.
6. Show up to 3–5 feasible alternatives plus baseline: lowest demand, lowest shortfall, best soil protection, lowest nitrogen demand, balanced.
7. Include absolute values, relative numerical comparisons, model-run agreement, operational trade-offs and explanations.

No divide-by-zero, missing-as-zero, unsupported crop rankings or percentages of actual fertilizer savings from ordinal scores. Model agreement is not probability.

## 9. Screens

- Map: Leaflet, anchors and nearest-anchor snap.
- Farm profile: farmer inputs.
- Resilience dashboard: baseline metrics, Time Machine, Blind Spots, optional replay.
- Compare adaptations: cards, historical/future switch, model-range bars.
- Collapsed evidence panel: NASA-derived/projected/modeled/rule-based tags, resolutions, citations, assumptions and optional satellite check.

## 10. Technology and data

Current scientific-correction milestone: the user's explicit instruction is to
repair the existing Python/FastAPI backend before frontend integration, preserving
one simulation implementation. Its current methods, API changes and limitations
are documented in [backend/SCIENTIFIC_VALIDITY.md](backend/SCIENTIFIC_VALIDITY.md).
No JavaScript port or duplicate simulation engine is part of this correction.

Static site, Leaflet, Chart.js, one JavaScript scientific engine, Python preprocessing (`requests`, `pandas`, `xarray`, `earthaccess` as needed). Cache environmental inputs, optionally ET0, offline. Run personalized simulations in JavaScript and cache repeated results if useful. Initial demo: SSP2-4.5, 2–3 models.

```text
data/
├── anchors/
│   ├── locations.json
│   └── <anchor_id>/
│       ├── historical.json
│       ├── future.json
│       └── metadata.json
├── crops.json
├── soil_texture.json
└── rotation_rules.json
```

## 11. Build plan (16 working hours)

Deadline: Sunday November 15, 2026, 11:59 p.m. local (team-provided).

| Hours | Work |
|---|---|
| 0–2 | Test POWER, GPM, projections; anchors, schemas, UI with labeled mock data |
| 2–5 | Extract data, cite crop/soil inputs, ET0, bucket, stress, cover, exposure |
| 5–8 | Rotation generation, constraints, scoring, historical/future runs |
| 8–11 | Connect map/form, Time Machine, Blind Spots, adaptation cards |
| 11–13 | Tests, evidence; optional MODIS and adverse-year replay only if core works |
| 13–16 | Feature freeze, seven-slide deck, backup video, link test and submission |

End-to-end application by hour 11. No new features after hour 13.

## 12. Priorities and fallback

P0: anchors, POWER + GPM (POWER precipitation fallback), future projections, farmer inputs, water balance, Time Machine, Blind Spots, feasible alternatives, evidence.

P1: MODIS, replay, SSP3-7.0, third climate model, frost/growing-season indicators, dominated-option pruning.

Post-MVP (deferred): SMAP observational cross-check only; retain existing artifacts, with no additional downloads or engine integration under the current scope.

SMAP is an independent stretch goal: its data and extraction dependencies are optional. Core backend operation and core test discovery must work without them. On the preserved SMAP branch, install `backend/requirements-smap.txt` only for explicitly scoped SMAP work; its offline loader uses the Python standard library and returns `None` for a missing anchor cache.

Cut order: pruning → frost → SSP3-7.0 → MODIS → replay → third model. SMAP is already deferred beyond the MVP. Reduce candidate count if slow. Protect scientific correctness and core features.

Out of scope: ECOSTRESS, ML, yield/profit, live imagery, accounts, multi-field and global expansion.

If projections cannot be extracted, run explicitly labeled sensitivity tests with temperature and precipitation perturbations. Never call synthetic scenarios NASA projections. If only one model is available, disclose that there is no multi-model range.

## 13. Demo

Seven slides or 30-second video: problem and pitch; NASA data fusion; map/profile/dashboard; Blind Spots; Time Machine and optional replay; adaptations and model agreement (optional satellite check); quantified modeled impact, assumptions and next steps. Show only implemented features and actual calculated results.

## 14. Tests

- Data: unique/aligned dates, correct units, precipitation >= 0, Tmax >= Tmin, no missing sentinels, correct model and scenario IDs.
- Engine: ET0 >= 0, 0 <= storage <= capacity, mass balance, shortfall >= 0, moisture carryover, winter wheat calendar, cover in [0,1], active cover crops contribute to demand.
- Recommendations: mandatory/avoided crops, equipment, zero baseline, null handling, independent model runs, fair starting phases.
