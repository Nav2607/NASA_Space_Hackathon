"""Screen existing daily diagnostics; no new stress physics or recommendation logic."""
import datetime as dt

import numpy as np

from . import climate_future, recommend as R
from .rotation_simulation import ASSUMPTIONS, ET0_METHOD, simulate_rotation
from .weather import load_reference, load_weather

EXPOSURES = ("water", "heat", "combined")
SCREENING_NOTE = (
    "Sensitive windows and heat thresholds are approximate screening assumptions, "
    "not observed phenology, crop damage thresholds or yield predictions. "
    "Water stress is the existing depletion-threshold indicator, distinct from unmet demand."
)


def detect_events(days):
    """Join only adjacent dates with the same crop and exclusive exposure type."""
    events = []
    for day in days:
        kind = day["stress_type"]
        if kind == "no_blind_spot":
            continue
        if (events and events[-1]["crop"] == day["crop"]
                and events[-1]["stress_type"] == kind
                and dt.date.fromisoformat(day["date"]) - dt.date.fromisoformat(events[-1]["end_date"])
                == dt.timedelta(days=1)):
            events[-1]["end_date"] = day["date"]
            events[-1]["duration_days"] += 1
            events[-1]["_days"].append(day)
        else:
            events.append({"start_date": day["date"], "end_date": day["date"],
                           "crop": day["crop"], "stress_type": kind, "duration_days": 1,
                           "_days": [day]})
    for event in events:
        samples = event.pop("_days")
        # Missing optional diagnostics in caller-supplied fixtures stay unknown.
        for output, key, reducer in (
            ("max_water_depletion_intensity", "water_depletion_intensity", max),
            ("mean_water_depletion_intensity", "water_depletion_intensity", np.mean),
            ("cumulative_unmet_demand_mm", "unmet_demand_mm", sum),
            ("cumulative_heat_exceedance_degree_days", "heat_exceedance_c", sum),
            ("max_temperature_c", "tmax_c", max),
        ):
            values = [day.get(key) for day in samples]
            event[output] = None if any(v is None for v in values) else float(reducer(values))
    return events


def present_phase(phase, first, last):
    # Daily diagnostics include a warm-up year; never expose/count it as evaluated data.
    frame = phase["daily"].loc[f"{first}-01-01":f"{last}-12-31"]
    days = []
    totals = dict.fromkeys(EXPOSURES, 0)
    for date, row in frame.iterrows():
        sensitive = bool(row.sensitive_window)
        water = sensitive and bool(row.critical_stress)
        heat = sensitive and bool(row.heat_stress)
        combined = water and heat
        kind = ("combined_heat_water" if combined else "water_stress" if water
                else "heat_exposure" if heat else "no_blind_spot")
        totals["water"] += int(water)
        totals["heat"] += int(heat)
        totals["combined"] += int(combined)
        days.append({"date": date.date().isoformat(), "crop": row.crop or None,
                     "sensitive_window": sensitive, "precip_mm": float(row.precip_mm),
                     "tmax_c": float(row.tmax_c), "storage_mm": float(row.storage_mm),
                     "unmet_demand_mm": float(row.shortfall_mm),
                     "water_stress": water, "heat_exposure": heat, "stress_type": kind,
                     "water_depletion_intensity": row.get("water_depletion_intensity"),
                     "heat_exceedance_c": row.get("heat_exceedance_c"),
                     "heat_threshold_c": (float(row.heat_threshold_c) if row.crop
                                          and "heat_threshold_c" in row else None)})
    events = detect_events(days)
    durations = [event["duration_days"] for event in events]
    return {"phase": phase["phase"], "first_crop": phase["first_crop"],
            "daily": days, "events": events,
            "event_statistics": {"event_count": len(events),
                                 "longest_event_duration_days": max(durations, default=0),
                                 "mean_event_duration_days": float(np.mean(durations)) if durations else None},
            "summary": {"total_days": totals,
                        "annualized_days": {key: value / (last - first + 1) for key, value in totals.items()}}}


def weekly_vulnerabilities(phases):
    """Equal climate-year weight; phases are alternative modeled placements, not observations.

    Eligibility requires sensitive crop days in that calendar week. Each phase
    first contributes one season indicator, then eligible phases are averaged
    within each crop/week/year, then years are averaged. Never pool phase-years.
    """
    season_phases = {}
    for phase in phases:
        groups = {}
        for day in phase["daily"]:
            if not day["crop"] or not day["sensitive_window"]:
                continue
            date = dt.date.fromisoformat(day["date"])
            key = (day["crop"], date.isocalendar().week, date.year)
            groups.setdefault(key, []).append(day)
        for key, days in groups.items():
            flags = {"water": any(d["water_stress"] for d in days),
                     "heat": any(d["heat_exposure"] for d in days),
                     "combined": any(d["water_stress"] and d["heat_exposure"] for d in days),
                     "any": any(d["water_stress"] or d["heat_exposure"] for d in days)}
            means = {}
            for output, field in (("mean_water_depletion_intensity", "water_depletion_intensity"),
                                  ("mean_heat_exceedance_c", "heat_exceedance_c"),
                                  ("mean_daily_unmet_demand_mm", "unmet_demand_mm")):
                values = [d.get(field) for d in days]
                means[output] = None if any(v is None for v in values) else float(np.mean(values))
            season_phases.setdefault(key, []).append({"flags": flags, **means})
    windows = {}
    for (crop, week, year), samples in season_phases.items():
        windows.setdefault((crop, week), []).append((year, samples))
    rows = []
    for (crop, week), seasons in sorted(windows.items()):
        n = len(seasons)
        equivalents = {key: sum(float(np.mean([p["flags"][key] for p in samples]))
                               for _, samples in seasons) for key in (*EXPOSURES, "any")}
        row = {"crop": crop, "calendar_week": week, "eligible_seasons": n,
               "eligible_season_years": sorted(year for year, _ in seasons),
               "seasons_with_exposure": {key: sum(any(p["flags"][key] for p in samples)
                                                  for _, samples in seasons)
                                         for key in (*EXPOSURES, "any")},
               "exposed_season_equivalents": equivalents,
               "frequency_pct": {key: 100 * equivalents[key] / n for key in EXPOSURES}}
        for metric in ("mean_water_depletion_intensity", "mean_heat_exceedance_c", "mean_daily_unmet_demand_mm"):
            values = [p[metric] for _, samples in seasons for p in samples]
            row[metric] = (None if any(v is None for v in values) else
                           float(np.mean([np.mean([p[metric] for p in samples]) for _, samples in seasons])))
        rows.append(row)
    return rows


def compare_weekly(historical, models):
    """Describe matched exposure frequencies, never calibrated probabilities."""
    def indexed(rows):
        return {(row["crop"], row["calendar_week"]): row for row in rows}
    baseline = indexed(historical)
    future = {name: indexed(rows) for name, rows in models.items()}
    keys = set(baseline).union(*(set(rows) for rows in future.values()))
    comparisons = []
    for crop, week in sorted(keys):
        key = (crop, week)
        item = {"crop": crop, "calendar_week": week}
        if not future or key not in baseline or any(key not in rows for rows in future.values()):
            comparisons.append({**item, "status": "insufficient_data", "exposures": None,
                                "reason": "Missing eligible historical or model seasons; not replaced with zero"})
            continue
        if (baseline[key]["eligible_seasons"] <= 0
                or any(rows[key]["eligible_seasons"] != baseline[key]["eligible_seasons"]
                       or rows[key].get("eligible_season_years") != baseline[key].get("eligible_season_years")
                       for rows in future.values())):
            comparisons.append({**item, "status": "insufficient_data", "exposures": None,
                                "reason": "Historical/model eligible seasons are not matched"})
            continue
        item.update(status="available", eligible_seasons=baseline[key]["eligible_seasons"], exposures={})
        for exposure in EXPOSURES:
            old = baseline[key]["frequency_pct"][exposure]
            values = {name: rows[key]["frequency_pct"][exposure] for name, rows in future.items()}
            changes = {name: value - old for name, value in values.items()}
            # Numerical tolerance only; no arbitrary scientific severity cutoff.
            agreement = {"increased": sum(v > 1e-9 for v in changes.values()),
                         "decreased": sum(v < -1e-9 for v in changes.values()),
                         "unchanged": sum(abs(v) <= 1e-9 for v in changes.values())}
            count = len(values)
            if old == 0 and agreement["unchanged"] == count:
                label = "no_exposure"
            elif old == 0 and agreement["increased"] == count:
                label = "emerging"
            elif old > 0 and agreement["decreased"] == count:
                label = "diminishing"
            elif old > 0 and agreement["decreased"] == 0:
                label = "persistent"
            else:
                label = "uncertain"
            median = float(np.median(list(values.values())))
            item["exposures"][exposure] = {
                "historical_frequency_pct": old, "future_frequency_pct_by_model": values,
                "future_median_frequency_pct": median,
                "future_range_frequency_pct": {"min": min(values.values()), "max": max(values.values())},
                "change_percentage_points": median - old, "change_percentage_points_by_model": changes,
                "model_agreement": agreement, "classification": label}
        comparisons.append(item)
    return comparisons


def _summarize(summaries, reducer):
    return {measure: {key: float(reducer([s[measure][key] for s in summaries]))
                      for key in EXPOSURES} for measure in ("total_days", "annualized_days")}


def blind_spots(request):
    anchor = R.snap(request["lat"], request["lon"])
    crops, soils = load_reference("crops"), load_reference("soil_texture")
    soil = request.get("soil", "loam")
    if soil not in soils or soil.startswith("_"):
        raise R.InputError("Unsupported soil texture")
    current = request.get("current_rotation") or list(R.DEFAULT_ROTATION)
    if any(crop not in R.rotations.MAIN_CROPS for crop in current):
        raise R.InputError("Blind Spots supports corn, soybean and winter_wheat only")
    rotation = tuple((crop, None) for crop in current)
    future = request.get("climate_period", "historical") == "future"
    first, last = {"2005_2024": (2005, 2024), "2005_2014": (2005, 2014),
                   "2015_2024": (2015, 2024)}[request.get("historical_period", "2005_2024")]
    result = {"status": "available", "anchor": anchor, "rotation": current,
              "default_rotation": not bool(request.get("current_rotation")),
              "climate_period": "future" if future else "historical",
              "runs": [], "summary": None, "et0_method": ET0_METHOD,
              "recurring_vulnerabilities": None, "emerging_vulnerabilities": [],
              "intensity_note": "Water intensity uses after-rain, before-ET depletion: excess above p*capacity divided by (1-p)*capacity, 0 at/below threshold and 1 at empty available storage. Heat exceedance is max(Tmax - existing heat threshold, 0). Neither predicts crop damage or yield.",
              "weekly_method": "ISO calendar week; sensitive-window days only; season year is the calendar year of the sensitive window. Average eligible phases within each crop/week/year, then give each eligible climate year equal weight. Phases are not independent observed years. Weekly exposure means at least one flagged day.",
              "screening_note": SCREENING_NOTE, "assumptions": list(ASSUMPTIONS),
              "summary_method": "Equal-weight phase mean; future summary is the median of independent model summaries.",
              "counting_note": "Water and heat counts each include combined days; combined is their intersection. Events use exclusive stress types.",
              "simulation_mode": "Rainfed; irrigation and tile drainage are context only. Farmer constraints and priorities do not filter this supplied comparison rotation."}
    try:
        weather = load_weather(anchor["id"])
        if future:
            doc = climate_future.deltas_at(anchor["lat"], anchor["lon"], "ssp245", "2031_2050")
            first, last = doc["baseline_period"]["start"], doc["baseline_period"]["end"]
            if last - first != 19 or not doc["models"]:
                raise ValueError("Future realization requires a matched 20-year reference and climate models")
            scenarios = doc["models"]
            result.update({"period": {"start": 2031, "end": 2050}, "scenario": "ssp245",
                           "grid_cell": doc["cell"], "climate_model_reference_period": doc["baseline_period"],
                           "weather_label": "Delta-adjusted historical weather sequences; not deterministic future forecasts",
                           "date_note": "Daily and event dates retain historical sequence dates, not projected future dates.",
                           "model_range_note": "Min/max describe model spread, not probabilities or confidence intervals."})
        else:
            scenarios = {None: None}
            result.update({"period": {"start": first, "end": last},
                           "weather_label": "NASA-derived POWER historical daily weather"})
        result["weather_sequence_period"] = {"start": first, "end": last}
        for model, deltas in scenarios.items():
            inputs = climate_future.apply_deltas(weather, deltas) if model is not None else weather
            run = simulate_rotation(inputs, anchor["lat"], rotation, crops, soils[soil],
                                    first, last, return_daily=True)
            phases = [present_phase(p, first, last) for p in run["phases"]]
            result["runs"].append({"model": model, "phases": phases,
                                   "weekly_vulnerabilities": weekly_vulnerabilities(phases),
                                   "summary": _summarize([p["summary"] for p in phases], np.mean)})
        summaries = [run["summary"] for run in result["runs"]]
        result["summary"] = _summarize(summaries, np.median)
        if future:
            result["model_range"] = {measure: {key: {"min": min(s[measure][key] for s in summaries),
                                                     "max": max(s[measure][key] for s in summaries)}
                                               for key in EXPOSURES} for measure in result["summary"]}
            # One matched, unadjusted run shared by all model comparisons. Do not
            # compare future reference sequences with a different selected decade.
            reference = simulate_rotation(weather, anchor["lat"], rotation, crops, soils[soil],
                                          first, last, return_daily=True)
            historical = weekly_vulnerabilities([present_phase(p, first, last) for p in reference["phases"]])
            result["emerging_vulnerabilities"] = compare_weekly(
                historical, {run["model"]: run["weekly_vulnerabilities"] for run in result["runs"]})
            result["comparison_note"] = "Matched unadjusted POWER reference versus each delta-adjusted realization on identical dates and phases. Empirical modeled exposure frequencies, not probabilities. Monthly factors do not project changed rainfall occurrence, event sequencing or precise future timing."
            result["classification_rules"] = {
                "emerging": "No historical exposure; every model increases exposure above zero.",
                "diminishing": "Historical exposure exists; every model decreases exposure.",
                "persistent": "Historical exposure exists; no model decreases exposure.",
                "uncertain": "Mixed model directions or only some models introduce exposure.",
                "no_exposure": "Zero historical and all-model future exposure.",
                "note": "Descriptive labels only, not statistical significance or probability. Direction equality tolerance is 1e-9 percentage points."}
        else:
            historical = result["runs"][0]["weekly_vulnerabilities"]
        result["recurring_vulnerabilities"] = {"historical_period": {"start": first, "end": last},
                                                "historical": historical}
    except (ValueError, KeyError, OSError) as err:
        result.update(status="insufficient_data", reason=str(err), runs=[], summary=None,
                      recurring_vulnerabilities=None, emerging_vulnerabilities=[])
        result.pop("model_range", None)
    return result
