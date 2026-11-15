"""Continuous daily rotations, equal-weight starting phases, one fixed soil bucket.

The one-year warm-up, 50% initial store and fixed 1 m representative depth are
explicit comparison assumptions, not measured farm properties. Bare/offseason
soil evaporation and snow storage are omitted: off-crop demand is zero and all
precipitation enters the bucket on its recorded day. No unsupported cover crop
is scored. These limitations must accompany results.
"""
import datetime as dt

import numpy as np
import pandas as pd

from .crop_water import kc_curve, plant_date_for_year
from .et0 import et0_hargreaves
from .water_balance import run_bucket
from .weather import validate_weather

ET0_METHOD = "FAO-56 Hargreaves; Ra MJ/m2/day converted to mm/day with 0.408"
ASSUMPTIONS = [
    "Fixed representative soil depth 1 m; initial storage 50% of capacity at the start of a one-year warm-up, independently for every phase and climate run.",
    "Off-crop evaporation omitted (zero modeled demand outside cash-crop calendars); stored water may be overestimated.",
    "All precipitation enters immediately; no snow accumulation/melt, frozen-soil infiltration, irrigation, runoff or tile drainage model.",
    "FAO single-Kc curves and fixed calendar windows are regional planning approximations, not temperature-driven phenology; wheat spans autumn to harvest without a separate dormancy model.",
    "Cover variants excluded from scoring because defensible demand/calendar inputs are incomplete.",
    "Depletion-threshold days and unmet-demand days are distinct modeled indicators, not crop survival or yield predictions.",
]


class CalendarError(ValueError):
    pass


def midpoint(window, year):
    if len(window) != 2:
        raise ValueError("Planting/harvest window requires two dates")
    a, b = (dt.date.fromisoformat(f"{year}-{value}") for value in window)
    if b < a:
        raise ValueError("Calendar window must be chronological within its year")
    return pd.Timestamp(a + (b - a) / 2)


def crop_dates(crop_id, previous_id, harvest_year, crops):
    crop = crops[crop_id]
    harvest = midpoint(crop["harvest_window"], harvest_year)
    autumn = int(crop["plant_window"][0][:2]) >= 8
    plant_year = harvest_year - int(autumn)
    plant = pd.Timestamp(plant_date_for_year(crop, plant_year))
    previous_harvest = midpoint(crops[previous_id]["harvest_window"], harvest_year - 1)
    if autumn:
        # Allow sowing later within the existing window after the preceding crop.
        plant = max(plant, previous_harvest + pd.Timedelta(days=1))
        latest = pd.Timestamp(f"{plant_year}-{crop['plant_window'][1]}")
        if plant > latest:
            raise CalendarError(f"{crop_id} planting window cannot follow {previous_id} harvest")
    if plant >= harvest or previous_harvest >= plant:
        raise CalendarError("Overlapping cash-crop calendar")
    return plant, harvest


def phase_calendar(index, rotation, crops, first_year, phase):
    coefficient = np.zeros(len(index))
    crop_ids = np.full(len(index), "", dtype=object)
    critical = np.zeros(len(index), dtype=bool)
    depletion = np.full(len(index), .5)
    heat = np.full(len(index), np.nan)
    for year in range(index[0].year, index[-1].year + 2):
        slot = (year - first_year + phase) % len(rotation)
        crop_id = rotation[slot][0]
        prev_id = rotation[(slot - 1) % len(rotation)][0]
        crop = crops[crop_id]
        plant, harvest = crop_dates(crop_id, prev_id, year, crops)
        active = (index >= plant) & (index <= harvest)
        if not active.any():
            continue
        if np.any(crop_ids[active] != ""):
            raise CalendarError("Cash crops overlap; cannot double count demand")
        curve, notes = kc_curve(crop, plant.date())
        if curve is None:
            raise ValueError(f"Insufficient crop data for {crop_id}: {notes}")
        # Continue the terminal value if calendar harvest is later than the curve.
        coefficient[active] = curve.reindex(index[active], method="ffill").to_numpy()
        crop_ids[active] = crop_id
        p = crop.get("depletion_fraction_p")
        if p is None or not np.isfinite(p) or not 0 <= p <= 1:
            raise ValueError(f"Missing or invalid depletion threshold for {crop_id}")
        depletion[active] = p
        window = crop.get("critical_window")
        if not window or crop.get("heat_threshold_c") is None:
            raise ValueError(f"Missing critical window/heat threshold for {crop_id}")
        md = index[active].strftime("%m-%d")
        critical[active] = (md >= window[0]) & (md <= window[1])
        heat[active] = crop["heat_threshold_c"]
    return coefficient, crop_ids, critical, depletion, heat


def simulate_rotation(weather, lat, rotation, crops, soil, start_year, end_year,
                      initial_fraction=.5, depth_m=1.0, return_daily=False):
    if not rotation or any(cover is not None for _, cover in rotation):
        raise ValueError("Cover crop demand is unsupported; exclude cover variants from scoring")
    if any(c not in crops for c, _ in rotation):
        raise ValueError("Unknown crop")
    awc = soil.get("available_water_mm_per_m")
    if awc is None or not np.isfinite(awc) or awc <= 0:
        raise ValueError("Missing or invalid available water capacity")
    if not np.isfinite(depth_m) or depth_m <= 0 or not np.isfinite(initial_fraction) or not 0 <= initial_fraction <= 1:
        raise ValueError("Invalid soil depth or initial storage fraction")
    if not isinstance(start_year, int) or not isinstance(end_year, int) or start_year > end_year:
        raise ValueError("Invalid evaluation period")
    start, end = f"{start_year - 1}-01-01", f"{end_year}-12-31"
    if (not isinstance(weather.index, pd.DatetimeIndex) or not weather.index.is_unique
            or not weather.index.is_monotonic_increasing):
        raise ValueError("Weather dates must be unique and chronological")
    frame = weather.loc[start:end]
    validate_weather(frame, start, end)
    index = frame.index
    reference_et = et0_hargreaves(frame.tmax_c, frame.tmin_c, lat, index.day_of_year)
    capacity = float(awc * depth_m)
    phases = []
    for phase in range(len(rotation)):
        kc, crop_ids, critical, depletion, heat = phase_calendar(index, rotation, crops, start_year, phase)
        demand = reference_et * kc
        bucket = run_bucket(demand, frame.precip_mm.to_numpy(), capacity,
                            initial_storage=initial_fraction * capacity)
        # Preserve the existing after-rain, before-ET threshold exactly. Intensity
        # normalizes only the depletion beyond that threshold; it does not alter ET.
        depletion_mm = capacity - np.minimum(bucket["initial_store"] + frame.precip_mm.to_numpy(), capacity)
        depletion_threshold_mm = depletion * capacity
        threshold = (depletion_mm > depletion_threshold_mm) & (kc > 0)
        intensity = np.divide(np.maximum(depletion_mm - depletion_threshold_mm, 0),
                              capacity - depletion_threshold_mm, out=np.zeros(len(index)),
                              where=(capacity > depletion_threshold_mm) & (kc > 0))
        heat_exceedance = np.where(kc > 0, np.maximum(frame.tmax_c.to_numpy() - heat, 0), 0)
        daily = pd.DataFrame({"crop": crop_ids, "kc": kc, "et0_mm": reference_et,
                              "demand_mm": demand, "actual_et_mm": bucket["eta"],
                              "shortfall_mm": bucket["shortfall"], "storage_mm": bucket["store"],
                              "initial_storage_mm": bucket["initial_store"], "drainage_mm": bucket["drainage"],
                              "precip_mm": frame.precip_mm, "tmax_c": frame.tmax_c,
                              "sensitive_window": critical, "mass_balance_error_mm": bucket["mass_balance_error"],
                              "depletion_mm": depletion_mm, "depletion_threshold_mm": depletion_threshold_mm,
                              "water_depletion_intensity": intensity, "heat_threshold_c": heat,
                              "heat_exceedance_c": heat_exceedance,
                              "threshold_stress": threshold, "critical_stress": threshold & critical,
                              "unmet_demand": bucket["shortfall"] > 1e-9,
                              "heat_stress": (frame.tmax_c.to_numpy() >= heat) & critical}, index=index)
        evaluated = daily.loc[f"{start_year}-01-01":]
        annual = []
        for year, group in evaluated.groupby(evaluated.index.year):
            annual.append({"year": int(year), "demand_mm": float(group.demand_mm.sum()),
                           "actual_et_mm": float(group.actual_et_mm.sum()),
                           "shortfall_mm": float(group.shortfall_mm.sum()),
                           "stress_days": int(group.threshold_stress.sum()),
                           "critical_stress_days": int(group.critical_stress.sum()),
                           "unmet_demand_days": int(group.unmet_demand.sum()),
                           "heat_stress_days": int(group.heat_stress.sum())})
        a = pd.DataFrame(annual)
        phases.append({"phase": phase, "first_crop": rotation[phase][0], "annual": annual,
                       "metrics": {"water_use_mm": float(a.demand_mm.median()),
                                   "actual_et_mm": float(a.actual_et_mm.median()),
                                   "shortfall_typical_mm": float(a.shortfall_mm.median()),
                                   "shortfall_dry_mm": float(a.shortfall_mm.quantile(.9)),
                                   "stress_days": float(a.stress_days.median()),
                                   "critical_stress_days": float(a.critical_stress_days.median()),
                                   "unmet_demand_days": float(a.unmet_demand_days.median()),
                                   "heat_stress_days": float(a.heat_stress_days.median()),
                                   "living_cover_fraction": float((evaluated.crop != "").mean())},
                       **({"daily": daily} if return_daily else {})})
    metrics = {key: float(np.mean([phase["metrics"][key] for phase in phases])) for key in phases[0]["metrics"]}
    return {"metrics": metrics, "phases": phases, "n_years": end_year - start_year + 1,
            "capacity_mm": capacity, "period": {"start": start_year, "end": end_year},
            "et0_method": ET0_METHOD, "phase_summary": "Equal-weight mean of independent phase-specific annual summaries; p90 is over years within each phase",
            "assumptions": list(ASSUMPTIONS)}
