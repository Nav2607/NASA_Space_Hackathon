# Climate Blind Spots: minimal frontend contract

`POST /blind-spots` screens **one supplied rotation** using the existing continuous
simulation and `return_daily=True`. Call it separately for the baseline and any
alternative. There is no recommendation generation or new scoring.

Run the existing API from the repository root:

```sh
.venv/bin/python -m uvicorn backend.api.main:app --port 8000
```

## Request

```json
{
  "lat": 43.55,
  "lon": -80.25,
  "soil": "loam",
  "current_rotation": ["corn", "soybean"],
  "climate_period": "historical",
  "historical_period": "2005_2014"
}
```

- The existing `/recommend` request fields are accepted. Constraints and priority
  fields do not filter or change this explicitly supplied comparison rotation.
  Irrigation and tile drainage remain context only; the simulation is rainfed.
- `current_rotation`: 1–4 supported cash-crop IDs, in chronological order.
  Missing/empty uses the existing corn–soybean default, labeled `default_rotation`.
  Covers/unknown crops are rejected; no new cover calculations are introduced.
- `climate_period`: `historical` (default) or `future`.
- `historical_period`: `2005_2024` (default), `2005_2014`, or `2015_2024`.
  Ignored for future runs, which use the existing matched reference sequence.
- Future requests use the committed SSP2-4.5 monthly change factors for the
  2031–2050 climate target and independently simulate all available models.
- Invalid inputs return HTTP 422. Missing data or infeasible crop calendars return
  HTTP 200 with `status: "insufficient_data"`, a reason, empty `runs`, and null
  `summary`. Do not treat unavailable data as zero exposure.

## Response example

Selected fields from the request above using committed Guelph weather; the
complete response includes every evaluated day, event and rotation phase.
Numbers below are rounded for readability.

```json
{
  "status": "available",
  "rotation": ["corn", "soybean"],
  "climate_period": "historical",
  "period": {"start": 2005, "end": 2014},
  "weather_sequence_period": {"start": 2005, "end": 2014},
  "summary": {
    "total_days": {"water": 168.0, "heat": 0.0, "combined": 0.0},
    "annualized_days": {"water": 16.8, "heat": 0.0, "combined": 0.0}
  },
  "runs": [{
    "model": null,
    "phases": [{
      "phase": 0,
      "first_crop": "corn",
      "daily": [{
        "date": "2005-07-10",
        "crop": "corn",
        "sensitive_window": true,
        "precip_mm": 0.18,
        "tmax_c": 34.52,
        "storage_mm": 60.7975,
        "unmet_demand_mm": 0.0,
        "water_stress": true,
        "heat_exposure": false,
        "stress_type": "water_stress"
      }],
      "events": [{
        "start_date": "2005-07-10",
        "end_date": "2005-07-15",
        "crop": "corn",
        "stress_type": "water_stress",
        "duration_days": 6
      }],
      "summary": {
        "total_days": {"water": 174, "heat": 0, "combined": 0},
        "annualized_days": {"water": 17.4, "heat": 0.0, "combined": 0.0}
      }
    }]
  }]
}
```

## Interpretation and chart wiring

- Select `runs[model].phases[phase].daily` for a timeline. Historical runs have
  `model: null`; future runs have named climate models. Every cyclic starting
  phase is preserved, with independent initialization and the existing warm-up.
  Warm-up dates are excluded from all returned timelines and counts.
- `crop` is null outside active cash-crop calendars. Sensitive-window and heat
  thresholds are **approximate screening assumptions**, not observed phenology,
  validated Ontario damage thresholds, or yield predictions.
- `water_stress` reuses the engine's sensitive-window depletion-threshold flag;
  `heat_exposure` reuses its sensitive-window heat flag. A day outside the
  sensitive window has neither flag, even when unmet demand is positive.
- Daily `stress_type` is `water_stress`, `heat_exposure`,
  `combined_heat_water`, or `no_blind_spot`. Events omit `no_blind_spot` and join
  adjacent calendar dates only when crop and stress type match. Durations include
  both endpoints. Events may cross a calendar-year boundary.
- `storage_mm` is end-of-day modeled plant-available water storage;
  `unmet_demand_mm` is potential demand minus actual ET. Threshold stress can
  occur while unmet demand is zero. Rainfall is `precip_mm` in mm/day and maximum
  temperature is `tmax_c` in degrees Celsius.
- Per-phase totals are integer sensitive-window day counts. Water and heat
  totals each **include combined days**; combined is their intersection, not an
  additional mutually exclusive total. Annualized counts divide by evaluated
  calendar years, including off-crop days/years in the denominator.
- Each run's summary is the equal-weight mean of its phase counts. Top-level
  summary is the median of those independent model summaries (one historical
  run). Thus summary totals can be fractional; do not sum phases as extra years.
  These are mean annual counts, not the annual-median metrics in `/recommend`.
- Future responses additionally include `scenario`, `grid_cell`,
  `climate_model_reference_period` and `model_range`, with min/max values for
  every total and annualized count after phase averaging. Model spread is not
  probability or a confidence interval.
- Future `period` is 2031–2050, but daily/event dates remain **1995–2014 reference
  sequence dates**. Display `weather_label` and `date_note`: these are
  **delta-adjusted historical weather sequences, not deterministic forecasts**.
  Do not relabel individual dates as future weather or average models into a
  single daily timeline. The method cannot project changed storm sequencing or
  heatwave persistence.

This prototype does not calculate protective ground cover, rainfall/erosion
exposure, severity scores, yield loss or disaster replay. Existing physics,
parameters, phase behavior and recommendations remain unchanged.
