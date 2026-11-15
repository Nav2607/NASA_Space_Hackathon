# Agronaut

Decision support for Southern Ontario farmers: **compare crop rotations under historical and projected climate**, using NASA data.
Built for NASA Space Apps 2026, challenge *Field Shift: Adapting Farms with NASA Data*.

A farmer picks a field on the map, enters their usual rotation, soil and constraints, and gets alternative rotations compared against their own plan. The comparison covers water demand, unmet water demand in a typical and a dry year, nitrogen need, soil cover, and pest/disease break. Results can be shown for historical weather or a 2031–2050 climate-model scenario.

> **Educational decision support, not agronomic advice.** It compares rotations *relative to each other*. It does not predict yield, profit or irrigation needs. Talk to a local agronomist.

## Run it

Requires Python 3.10+ and an internet connection (map tiles and place search).

```bash
pip install -r backend/requirements.txt
python -m uvicorn backend.api.main:app --port 8000
```

Open **http://localhost:8000/**. One server provides both the web app and the API. Interactive API docs are at http://localhost:8000/docs.

Tests: `pip install -r backend/requirements-dev.txt` then `python -m pytest backend/tests`.

## How it works

1. **Weather:** NASA POWER daily data (1981–2024) is cached for 12 anchor locations across Southern Ontario. A clicked point uses its nearest anchor.
2. **Water model:** FAO-56 Penman-Monteith reference evapotranspiration, single-Kc crop curves and a root-zone soil-water bucket. A simulation runs for every anchor, soil, crop and weather year, and the results are precomputed.
3. **Rotations:** the model builds candidate rotations from corn, soybean and winter wheat (with cover-crop variants), applies the farmer's must-grow, avoid and equipment limits, scores them with the farmer's priorities, and returns up to five labelled options (for example "lowest potential water demand").
4. **Climate projections:** NASA NEX-GDDP-CMIP6 (SSP2-4.5, 2031–2050) supplies monthly change factors from three models, each compared with its own 1995–2014 baseline. Models are kept separate rather than averaged away.
5. **Blind spots:** `POST /blind-spots` screens one rotation for days of recurring vulnerability and stress intensity (see `backend/BLIND_SPOTS_API.md`).

## Data sources

| Source | Used for |
|---|---|
| NASA POWER | Daily temperature, rain, humidity, wind, sunlight (about 50 km grid) |
| NASA NEX-GDDP-CMIP6 | Projected monthly climate change factors, 0.25° grid |
| FAO Irrigation and Drainage Paper 56 | Evapotranspiration method, crop coefficients, stage lengths, rooting depth |
| AquaCrop default parameters | Soil water holding capacity by texture, crop heat limits |
| AAFC annual crop inventory | Crop-map extraction pipeline (`backend/data_scripts/extract_aafc.py`) |
| OpenFreeMap / OpenStreetMap | Basemap and place search |

Reference tables are in `backend/data/reference/`, each value with a source. Anything without a source is stored as unknown, and assumptions are labelled "Assumed" in the output.

## API

| Endpoint | Purpose |
|---|---|
| `GET /health` | Liveness check |
| `GET /anchors`, `GET /snap` | The 12 data points; which one a location uses |
| `GET /reference` | Soils, crops and equipment options for the form |
| `POST /recommend` | Compare rotations (`climate_period`: `historical` or `future`) |
| `POST /blind-spots` | Vulnerability screening for one rotation |
| `GET /evidence` | Data sources, citations, assumptions and limitations |

## Limitations (please read)

- Weather is regional (about 50 km), not measured on the field.
- The water model is simplified: fixed 1 m soil depth, rainfed only (irrigation and tile drainage are context, not simulated), no snow, runoff or water table.
- Water use for cover crops is not modelled, so cover crops are excluded from the scored alternatives.
- Nitrogen, soil-cover and pest-break ratings are qualitative and rule-based. Some thresholds and crop calendars are assumptions.
- There is no yield data, so lower water use does not mean a better rotation.
- NEX projections are model scenarios, not forecasts. They are applied as monthly change factors to historical weather.
- The form collects some inputs the model does not use yet (planting dates, budget, slope, irrigation limits). Sandy and silt loam soils are mapped to the nearest modelled soil, and the user is told.

Full detail: `backend/SCIENTIFIC_VALIDITY.md` and `GET /evidence`.

## AI use

AI coding assistance (Claude) helped build the backend and the integration. The numbers the app shows come from the cited data and the model code. No AI-generated values are used as data.
