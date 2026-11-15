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
        else:
            events.append({"start_date": day["date"], "end_date": day["date"],
                           "crop": day["crop"], "stress_type": kind, "duration_days": 1})
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
                     "water_stress": water, "heat_exposure": heat, "stress_type": kind})
    return {"phase": phase["phase"], "first_crop": phase["first_crop"],
            "daily": days, "events": detect_events(days),
            "summary": {"total_days": totals,
                        "annualized_days": {key: value / (last - first + 1) for key, value in totals.items()}}}


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
                                   "summary": _summarize([p["summary"] for p in phases], np.mean)})
        summaries = [run["summary"] for run in result["runs"]]
        result["summary"] = _summarize(summaries, np.median)
        if future:
            result["model_range"] = {measure: {key: {"min": min(s[measure][key] for s in summaries),
                                                     "max": max(s[measure][key] for s in summaries)}
                                               for key in EXPOSURES} for measure in result["summary"]}
    except (ValueError, KeyError, OSError) as err:
        result.update(status="insufficient_data", reason=str(err), runs=[], summary=None)
    return result
