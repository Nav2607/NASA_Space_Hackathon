# Corrected backend scientific contract

This task corrects the existing Python/FastAPI engine at the user's explicit
request. It does not implement a second engine or port to JavaScript. The v5
JavaScript architecture remains a separate deployment decision; this work is
scoped to the existing backend before frontend integration.

## Runtime and preserved artifacts

Install `backend/requirements.txt`; use `backend/requirements-dev.txt` for tests
and the existing offline extraction tools. Run from the repository root:

```sh
python -m pytest backend/tests -q
python backend/data_scripts/validate_reference.py
python -m uvicorn backend.api.main:app --port 8000
```

No runtime NASA requests occur. Existing POWER CSVs, London NEX demo, the
2041–2060 regional cache and pre-correction processed CSV/map summary are
preserved. The latter are legacy artifacts and no longer feed the recommendation
or map API. The corrected runtime computes continuous rotations from weather,
with in-process memoization. `build_metrics.py` now writes a separate version-2
rotation diagnostic JSON and refuses to overwrite the two legacy processed files.
SMAP remains deferred on `origin/smap`, commit `2e03043`.

## Water and calendar method

`rotation_simulation.py` is the authoritative path. Daily water accounting uses:

```
A = S + P
ETa = min(ETc, A)
U = ETc - ETa
D = max(0, A - ETa - C)
S_next = A - ETa - D
```

Every input must be finite and physically bounded. No missing weather is replaced
with zero. Every day satisfies `S + P = ETa + D + S_next` to floating-point
tolerance. Threshold stress is a separate depletion indicator and does not reduce
uptake in this intentionally simple bucket. Unmet-demand days are reported
separately. No metrics assert crop survival, yield or actual irrigation needs.

Capacity is soil available water per metre times a **fixed representative 1 m
soil depth**. Initial storage is 50% of that capacity at January 1 of a one-year
warm-up. Each starting phase and climate run gets the same initialization policy;
there are no crop, season, or year resets. All cyclic starting phases are run
independently without reordering the rotation. Annual medians and p90 shortfall
are computed within each phase, then given equal weight across phases. The
reported p90 is the mean of phase-specific annual p90s, not a new percentile
computed after averaging all phases' weather or outcomes. Phases and annual
results are retained in the Time Machine payload for inspection.
Summary medians of ETc, actual ET and shortfall need not satisfy an additive
identity; mass conservation is verified on the underlying daily runs, not by
subtracting independently summarized medians.

Cash crops use the existing planting/harvest window midpoints and FAO Kc curves.
For autumn wheat, planting follows the preceding crop's harvest, delayed if
necessary within its existing planting window. Infeasible harvest/planting
transitions are rejected for alternatives. Wheat remains in the daily calendar
from the preceding autumn through harvest. If a supplied baseline calendar is
infeasible, its original rotation is returned with null metrics and an explicit
insufficient-data reason; no substitute rotation is fabricated.

FAO Table 12 group values supply corn initial Kc 0.30 (Cereals) and soybean 0.40
(Legumes); the prior universal assumed 0.4 fallback is removed. Source:
https://www.fao.org/4/x0490e/x0490e0b.htm . Stage lengths remain cold-climate
analogues rather than Ontario-calibrated phenology. Curves stop at harvest or
retain their terminal coefficient if their nominal stage duration ends before
calendar harvest; this calendar approximation is a limitation.

Cover-crop coefficients/calendars remain incomplete. **No cover variants are
scored**, regardless of willingness to plant covers. Requiring rye or clover
returns insufficient feasible alternatives, preserving the mandatory crop ID.
There is no water-free cover benefit in recommendations. A supported baseline
remains visible even if it conflicts with new must/avoid/equipment constraints.
Unknown must-grow crops are never dropped. Unknown avoid IDs and equipment IDs
are input errors. Stored minimum-gap and banned-succession rules are enforced for
alternatives, and actual calendar compatibility is checked. Some stored rules
still need Ontario citations; these are conservative prototype constraints, not
verified agronomic prescriptions. Uncited blanket legume nitrogen credits are
not applied. Base nitrogen classes remain ordinal rule-based indicators.

## Climate Time Machine

Historical periods are exactly 2005–2014 and 2015–2024. The requested future
period is exactly **2031–2050**, SSP2-4.5. The 2041–2060 cache is not relabeled or
used as a substitute. All historical and future runs use FAO-56 Hargreaves with
`Ra` in MJ/m²/day converted to equivalent mm/day using **0.408** before the
0.0023 formula. Negative ET0 is floored at zero; missing temperatures remain
missing and stop the simulation.

For future runs, the regional extraction compares each model's future climate
against that same model's reference period. The matching POWER reference years
(default 1995–2014, with 1994 warm-up) provide the daily event sequence. Changes
are applied separately for each model, never to ensemble-median climate inputs:

- Add the average of Tmax/Tmin monthly deltas to historical mean temperature.
- Multiply each historical daily diurnal range by the model's future/reference
  monthly diurnal-range ratio; reconstruct Tmax/Tmin around the adjusted mean.
- Multiply historical precipitation by that model's monthly precipitation ratio.

Using a modeled DTR ratio avoids the inverted daily temperature ranges possible
with separate additive Tmax/Tmin changes; missing or invalid ratios are errors.
This is a documented change-factor approximation derived from NEX, not an
additional NASA dataset or a NASA-provided daily forecast. Old caches without
DTR retain the legacy additive path, but inversions are rejected, not clipped.

Simulate every model independently, including all rotation starting phases.
Then report the median model outcome and minimum/maximum model outcomes for
each metric, along with the full named model results. Each model gets equal
weight. No model-agreement percentage is interpreted as probability. The
matched reference controls the change-factor comparison; it is not a claim of
complete bias correction or removal of all POWER/NEX differences.

Delta-adjusted weather retains the historical dates, wet/dry-event order and
variability. The payload distinguishes `period` (2031–2050 climate target) from
`weather_sequence_period` (reference dates used). It cannot project changes in
storm sequencing, interannual variability or future heatwave persistence.

A missing/invalid 2031–2050 cache produces `future_2031_2050.status =
"insufficient_data"`, null future metrics and a reason. A request to score future
conditions in that case returns no scored alternatives and
`scores_available = false`; the historical baseline remains explicitly labeled.

## API changes for frontend integration

The existing endpoints and basic request fields remain. Additional request fields:

- `climate_period`: `"historical"` (default, full 2005–2024 comparison) or
  `"future"` (2031–2050 model-median outcome scoring).
- `allow_cover_crops`: accepted for compatibility/context; variants remain
  unavailable until demand inputs are defensible.

Unknown request fields, invalid coordinates and invalid priority values are
rejected with 422. `/snap` checks finite coordinates, a coarse Southern Ontario
bounding box and anchor distance; it is not a land-parcel or lake mask.

Recommendations add `status`, `reason`, `feasible_alternative_count`,
`scoring_period`, `scores_available`, `rejected_alternatives`, and `time_machine`.
A valid request may return HTTP 200 with `status =
"insufficient_feasible_alternatives"`, fewer than three feasible alternatives
(or none), and the original baseline. Clients must inspect status, not assume
five options. Input contradictions still return 422. Missing baseline essentials
return `status = "insufficient_data"`, original rotation and null metrics.
Each baseline/option includes `metrics_period` identifying which climate period
its headline metrics actually describe. If future scores are unavailable,
the baseline metrics remain historical and explicitly labeled.

The existing `water_use_mm` means **potential demand**, not actual consumption;
`potential_demand_mm` is an explicit alias. `actual_et_mm` is separate.
`survived_years`, severe-stress proxy fields and generic 30°C fields are removed.
Use `threshold_stress_days_typical`, `critical_stress_days_typical`,
`unmet_demand_days_typical`, and crop-specific `heat_stress_days_typical`.
`years_simulated` is the climate-window length, not phase count times years.
Ordinal nitrogen differences are not fertilizer savings percentages.

`labels` can list several criteria won by one option. An option is only labeled
lowest/best if it actually wins that criterion among feasible options. Other
feasible rotations use `additional_alternative`; no false winner labels are
assigned merely to produce five distinct cards. A zero baseline demand yields
null relative demand percentage rather than an invented 100%.

`charts.typical_vs_dry_by_crop` and `metrics.by_crop` remain empty compatibility
objects: independent crop summaries must not be presented as chronological
rotation results. Use period/phase/annual results from `time_machine`. Daily
water/calendar diagnostics are available from the engine's `return_daily=True`
mode and now through `POST /blind-spots`; see
[BLIND_SPOTS_API.md](BLIND_SPOTS_API.md) for the daily/event contract and count
aggregation. This endpoint only screens existing flags; there is no fabricated
rainfall-exposure or erosion metric.

## Remaining scientific limitations

- Off-crop soil evaporation is omitted (explicit zero modeled demand outside
  cash-crop calendars); this can overestimate retained soil water. This is a
  missing process, not an imputed observation. A defensible bare-soil model is
  still needed before field-level interpretations.
- No snow accumulation/melt or frozen-soil infiltration model: recorded winter
  precipitation enters immediately. No separate wheat dormancy model.
- Fixed root-zone depth and initialization are comparison assumptions; soils
  are texture presets rather than measured farm properties.
- POWER precipitation is the explicitly labeled fallback; GPM is not added.
- Local crop calendars, critical-stage thresholds and some compatibility rules
  need stronger Ontario-specific sourcing. Regional output is not validation.
- Minimal daily Blind Spots screening is exposed; residue/protective-cover
  fractions and rainfall-exposure indicators remain deferred.

Physical invariants and explicit data availability are tested; passing tests is
not field validation. Do not claim yield, crop survival, measured savings or a
precise future weather forecast.

## Verification completed for this correction

Checkpoint preparation commands (from repository root):

```sh
python -m pip install -r backend/requirements-dev.txt
# Existing daily POWER inputs, if rebuilding rather than using committed CSVs:
python backend/data_scripts/fetch_power.py
# Rebuild the committed exact-period regional future cache (offline-preparation network step):
python backend/data_scripts/extract_nex_region.py --baseline 1995 2014 --future 2031 2050 --scenario ssp245
# Optional diagnostic output; not required to run the API:
python backend/data_scripts/build_metrics.py --anchor guelph --soil loam --output backend/data/processed/rotation_metrics_v2.json
```

Runtime-required POWER CSVs, reference tables, anchor coordinates and the
2031–2050 future cache are included in Git. Intermediate `.nex-cache/` and
`.smap-cache/` files are excluded and not needed for runtime operation. The
version-2 diagnostic output is reproducible and optional; the API computes
corrected results directly from the committed inputs.

- `python -m pytest backend/tests -q`: **73 passed** (12.18 seconds in the final run).
- `python backend/data_scripts/validate_reference.py`: **0 errors**, 16 remaining
  null reference fields, all for excluded red-clover/cereal-rye modeling inputs.
- `python -m compileall -q backend` and `git diff --check`: passed.
- Historical corn–soybean–wheat, 2005–2024: all 12 anchors × four soil textures ×
  three phases passed storage/ET bounds and daily mass checks. Maximum reported
  absolute daily mass residual was 0 mm at floating-point precision in these runs.
- Real future runs: all 12 anchors had complete monthly factors and successful
  independent runs for ACCESS-CM2, MPI-ESM1-2-HR and MRI-ESM2-0. SSP2-4.5,
  2031–2050 target, 1995–2014 matched reference; regional grid 18 × 38.
- Fresh ASGI requests for all three archived example requests, in both historical
  and future modes, returned HTTP 200 with finite JSON. Guelph and London yielded
  four options; the constrained Barrie soybean request yielded two with explicit
  insufficient-feasible-alternatives status. Original baselines remained present.
- Version-2 preparation smoke test wrote four continuous rotations and seven
  calendar rejections to a temporary review artifact, preserving old outputs.
- SHA-256 checks confirmed all pre-existing weather, climate and processed data
  files unchanged. Only the intended two initial-Kc reference values and their
  basis text changed in existing reference data; the exact-period climate cache
  is a new file. This verification preceded the user-authorized backend checkpoint.

Files changed/added for review:

- Engine: `rotation_simulation.py` (new), `water_balance.py`, `et0.py`,
  `crop_water.py`, `weather.py`, `climate_future.py`, `rotations.py`, `ratings.py`,
  `recommend.py` under `backend/engine/`.
- API: `backend/api/main.py`.
- Preparation: `fetch_power.py`, `extract_nex_region.py`, `build_metrics.py` under
  `backend/data_scripts/`.
- Data: `backend/data/reference/crops.json` and new
  `backend/data/nex/delta_ssp245_2031_2050.json`.
- Tests: updated `test_et0.py`, `test_water_balance.py`, `test_recommend.py`,
  `test_climate_future.py`; new `test_scientific_validity.py`,
  `test_nex_validation.py`, and `fixtures/README.md` under `backend/tests/`.
- Setup/documentation: `backend/requirements.txt`, `backend/requirements-dev.txt`,
  this document, `backend/NEX_SETUP`, `backend/BACKEND_PLAN.md`, `PROJECTS.md`,
  `AGENTS.md`, and `TASKS.md`. Previously uncommitted ignore rules were preserved.

Readiness: the corrected baseline, constrained recommendation and Time Machine
API contracts are ready for frontend wiring with these limitations displayed.
No climate-data blocker remains for these anchors/scenario. Full dashboard
completion still needs frontend Blind Spots wiring and defensible rainfall-exposure inputs, and
scientific refinements above remain necessary before agronomic or field-level
claims. A JavaScript migration remains outside this user-authorized correction.
