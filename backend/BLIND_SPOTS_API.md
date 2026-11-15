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

## Incremental vulnerability-analysis fields

The request and every existing response field remain compatible. No new inputs
are required. The following additions use the same daily simulation results.

### Daily intensity and event characteristics

Each daily row adds `water_depletion_intensity`, `heat_exceedance_c` and
`heat_threshold_c` (null outside the crop calendar). Daily unmet demand remains
`unmet_demand_mm`.

Water intensity uses the **exact existing engine threshold**, not end-of-day
storage. With capacity C, previous end-of-day storage S, precipitation P and the
existing crop depletion fraction p:

```text
depletion = C - min(S + P, C)                 # after rain, before ET
water stress = depletion > p*C, with Kc > 0  # existing strict comparison
intensity = max(depletion - p*C, 0) / (C - p*C)
```

Intensity is dimensionless, from 0 at/below the threshold to 1 at empty available
storage. Off-crop intensity is 0. For the degenerate p=1 case, intensity is 0
because the existing threshold cannot be exceeded. This diagnostic does not
change uptake, storage, ET or flags. The engine exposes the depletion and
threshold diagnostics alongside intensity internally, so the API does not
reimplement the physical calculation.

Heat exceedance is `max(Tmax - heat_threshold_c, 0)` in degrees Celsius on active
crop days. The original heat flag uses **>=**: a day exactly at the threshold is
exposed with zero exceedance. Daily intensities are available outside sensitive
windows too, but flags, events and weekly aggregation remain restricted to the
existing sensitive windows.

Events add the following fields. This is an actual Guelph future ACCESS-CM2
phase-0 event, rounded for display:

```json
{
  "start_date": "1995-07-15",
  "end_date": "1995-08-05",
  "crop": "corn",
  "stress_type": "water_stress",
  "duration_days": 22,
  "max_water_depletion_intensity": 1.0,
  "mean_water_depletion_intensity": 0.65582,
  "cumulative_unmet_demand_mm": 36.11539,
  "cumulative_heat_exceedance_degree_days": 0.0,
  "max_temperature_c": 37.95888
}
```

Heat degree-days sum daily **maximum-temperature** exceedance times one day;
this is a screening proxy, not an hourly integrated heat dose. Event means and
sums cover only the event's days. A water-only event can have positive intensity
and zero unmet demand. Intensity never means crop damage, yield loss, or a new
composite score.

Each phase adds `event_statistics`:

```json
{
  "event_count": 23,
  "longest_event_duration_days": 32,
  "mean_event_duration_days": 19.0
}
```

These statistics describe the existing exclusive crop/type events. A change of
stress type ends an event even if another exposure starts the next day. No-event
phases have count/longest 0 and mean null. Phases and models are not pooled into
one artificial continuous event.

### Recurring weekly vulnerability heatmaps

Each `runs[]` entry adds `weekly_vulnerabilities`, a list keyed by `crop` and
`calendar_week`. Top-level `recurring_vulnerabilities` contains
`historical_period` and `historical` rows. Historical requests use the selected
period; future requests use the **unadjusted matched 1995–2014 POWER reference**,
not a different user-selected historical decade.

Eligibility means at least one sensitive-window day for that crop in that ISO
week and calendar year. A crop's absent years and weeks without sensitive days
are excluded. The current sensitive windows occur in spring/summer, so the
calendar year identifies the crop's reproductive season, including wheat
planted in the previous autumn. ISO week numbers are 1–53; partial weeks at
window boundaries may have fewer eligible seasons.

Within each crop/week/year, each eligible phase supplies a binary indicator of
at least one exposure day. Eligible phases are averaged **within that year**,
then eligible climate years receive equal weight. This does not turn rotation
phases into additional independent observed years. Repeated crop placements
retain their different modeled storage histories.

- `eligible_seasons`: number of unique eligible calendar years across phases.
- `seasons_with_exposure`: number of those years with exposure in **any** eligible
  phase. Includes water, heat, combined and any-exposure counts.
- `exposed_season_equivalents`: sum of within-year phase-averaged indicators.
  May be fractional; this, divided by `eligible_seasons` and multiplied by 100,
  produces `frequency_pct`. The any-phase count is not its numerator.
- `mean_water_depletion_intensity`, `mean_heat_exceedance_c`, and
  `mean_daily_unmet_demand_mm`: means over all eligible sensitive days, including
  unexposed days, first within a phase-season/week, then eligible phases, then
  years. They are not means only over stressed days. Unknown diagnostics remain
  null rather than being replaced by zero.
- Combined exposure requires water and heat on the **same day**, not merely
  different days within the same week. Frequency means seasons with at least
  one exposure day, not the percentage of days exposed.

Actual matched-reference Guelph corn, week 30 (selected fields, rounded):

```json
{
  "crop": "corn",
  "calendar_week": 30,
  "eligible_seasons": 20,
  "seasons_with_exposure": {"water": 13, "heat": 0, "combined": 0, "any": 13},
  "exposed_season_equivalents": {"water": 13.0, "heat": 0.0, "combined": 0.0, "any": 13.0},
  "frequency_pct": {"water": 65.0, "heat": 0.0, "combined": 0.0},
  "mean_water_depletion_intensity": 0.26809,
  "mean_heat_exceedance_c": 0.0,
  "mean_daily_unmet_demand_mm": 0.12523
}
```

These are empirical **modeled exposure frequencies**, not observed farm damage
frequencies or calibrated probabilities. Weeks with only a small number of
eligible days/seasons should not be interpreted as equally well supported as
full-window weeks. `eligible_season_years` lists the contributing climate years.

### Emerging future vulnerability comparisons

Future requests add `emerging_vulnerabilities`: rows keyed by crop/week, with
separate `water`, `heat` and `combined` entries under `exposures`. All three
existing models run independently. One additional unadjusted reference
simulation is shared by all three comparisons; existing model results are
reused. Historical requests leave this list empty and do not run future models.

The Guelph week-30 example's water entry is:

```json
{
  "historical_frequency_pct": 65.0,
  "future_frequency_pct_by_model": {
    "ACCESS-CM2": 65.0,
    "MPI-ESM1-2-HR": 60.0,
    "MRI-ESM2-0": 65.0
  },
  "future_median_frequency_pct": 65.0,
  "future_range_frequency_pct": {"min": 60.0, "max": 65.0},
  "change_percentage_points": 0.0,
  "change_percentage_points_by_model": {
    "ACCESS-CM2": 0.0,
    "MPI-ESM1-2-HR": -5.0,
    "MRI-ESM2-0": 0.0
  },
  "model_agreement": {"increased": 0, "decreased": 1, "unchanged": 2},
  "classification": "uncertain"
}
```

`change_percentage_points` is future model median minus historical frequency,
not relative percentage change. Simple descriptive classifications are returned
in `classification_rules`:

| Label | Rule |
|---|---|
| `emerging` | Historical frequency is zero; every model increases it above zero. |
| `diminishing` | Historical frequency is positive; every model decreases it. |
| `persistent` | Historical frequency is positive; no model decreases it. |
| `uncertain` | Other outcomes, including mixed directions or only some models introducing exposure. |
| `no_exposure` | Historical and every future-model frequency are zero. |

Direction comparisons use a numerical tolerance of 1e-9 percentage points only;
there is no significance test, severity threshold or probability interpretation.
A missing crop/week or mismatched eligible seasons returns row-level
`status: "insufficient_data"` and null `exposures`, never zero substitution.

All comparisons retain fixed estimated calendars and historical daily event
order. They cannot establish precise future timing, changed rainfall occurrence,
future phenology, or climate-model changes in storm/heatwave persistence.
