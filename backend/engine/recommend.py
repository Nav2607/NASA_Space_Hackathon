"""Evaluate rotations, score them against the farmer's own rotation, and build the API response."""
import math
from functools import lru_cache

import numpy as np
import pandas as pd

from . import ratings, rotations
from .water_balance import SEVERE_SHORTFALL_FRACTION
from .weather import DATA_DIR, load_anchors, load_reference

MAX_SNAP_KM = 150.0
DEFAULT_ROTATION = ["corn", "soybean"]
DEFAULT_PRIORITIES = {"water": 0.25, "nitrogen": 0.25, "soil_cover": 0.25, "weather_risk": 0.25}
CROP_NAMES = {"corn": "corn", "soybean": "soybean", "winter_wheat": "winter wheat",
              "red_clover": "red clover", "cereal_rye": "cereal rye"}
LABEL_TEXT = {"lowest_water": "Lowest water use", "lowest_nitrogen": "Lowest nitrogen demand",
              "best_soil_cover": "Best soil cover", "lowest_dry_year_risk": "Lowest dry-year risk",
              "balanced": "Balanced"}
SOURCES = {"water_use": "Simulated (NASA POWER weather + FAO-56 method)",
           "dry_year_shortfall": "Simulated (NASA POWER weather + FAO-56 method)",
           "stress_days": "Simulated", "weather": "NASA-derived (POWER, about 50 km grid)",
           "nitrogen": "Rule-based", "soil_cover": "Rule-based (crop calendars, assumed dates)",
           "pest_break": "Rule-based", "survival": "Simulated; threshold assumed"}


class InputError(ValueError):
    pass


def round5(x):
    return int(5 * round(x / 5))


def haversine_km(lat1, lon1, lat2, lon2):
    p1, p2 = math.radians(lat1), math.radians(lat2)
    a = math.sin((p2 - p1) / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(math.radians(lon2 - lon1) / 2) ** 2
    return 12742 * math.asin(math.sqrt(a))


def snap(lat, lon):
    anchors = load_anchors()
    best = min(anchors, key=lambda a: haversine_km(lat, lon, anchors[a]["lat"], anchors[a]["lon"]))
    dist = haversine_km(lat, lon, anchors[best]["lat"], anchors[best]["lon"])
    if dist > MAX_SNAP_KM:
        raise InputError(f"This point is {dist:.0f} km from the nearest data point; the app covers Southern Ontario only.")
    return {"id": best, "lat": anchors[best]["lat"], "lon": anchors[best]["lon"], "distance_km": round(dist, 1)}


@lru_cache(maxsize=1)
def _metrics_table():
    df = pd.read_csv(DATA_DIR / "processed" / "crop_year_metrics.csv")
    return {key: g.set_index("year") for key, g in df.groupby(["anchor", "soil", "crop"])}


@lru_cache(maxsize=1)
def _reference():
    return load_reference("crops"), load_reference("soil_texture"), load_reference("rotation_rules")


def evaluate(anchor, soil, rotation):
    """Water/stress metrics for a rotation: every crop in the cycle sees the same weather year,
    the cycle's yearly average is taken, then median (typical) and 90th percentile (dry) over years."""
    table = _metrics_table()
    per_crop = {}
    for crop, _ in rotation:
        if (anchor, soil, crop) not in table:
            return None
        per_crop[crop] = table[(anchor, soil, crop)]
    years = sorted(set.intersection(*[set(t.index) for t in per_crop.values()]))
    if len(years) < 10:
        return None

    def stack(col):
        return np.array([[per_crop[c].loc[y, col] for c, _ in rotation] for y in years])
    etc, short = stack("etc_mm"), stack("shortfall_mm")
    severe, hot = stack("severe_stress_days"), stack("hot_days_30c_critical")
    etc_y, short_y = etc.mean(axis=1), short.mean(axis=1)
    pct_y = short.sum(axis=1) / etc.sum(axis=1)
    dry_cut = np.quantile(short_y, 0.9)
    dry = short_y >= dry_cut

    by_crop = {}
    for c in dict.fromkeys(c for c, _ in rotation):
        t = per_crop[c]
        by_crop[c] = {"water_use_mm": round(float(t["etc_mm"].median())),
                      "shortfall_typical_mm": round(float(t["shortfall_mm"].median())),
                      "shortfall_dry_mm": round(float(t["shortfall_mm"].quantile(0.9)))}
    return {
        "n_years": len(years),
        "water_use_mm": float(np.median(etc_y)),
        "shortfall_typical_mm": float(np.median(short_y)),
        "shortfall_dry_mm": float(dry_cut),
        "severe_stress_days_typical": float(np.median(severe.mean(axis=1))),
        "severe_stress_days_dry": float(severe.mean(axis=1)[dry].mean()),
        "hot_days_30c_typical": float(np.median(hot.mean(axis=1))),
        "survived_years": int((pct_y <= SEVERE_SHORTFALL_FRACTION).sum()),
        "dry_shortfall_share": float(dry_cut / np.median(etc_y)),
        "by_crop": by_crop,
    }


def _has_repeat(rotation):
    return any(rotation[i - 1][0] == rotation[i][0] for i in range(len(rotation)))


def _describe(rotation):
    return [{"crop": c, "cover_crop": cv} for c, cv in rotation]


def _name(rotation):
    parts = []
    for c, cv in rotation:
        parts.append(CROP_NAMES[c] + (f" + {CROP_NAMES[cv]}" if cv else ""))
    return " → ".join(parts)


def build_entry(anchor, soil, rotation):
    m = evaluate(anchor, soil, rotation)
    if m is None:
        return None
    crops, _, rules = _reference()
    r = ratings.rate(rotation, crops, rules)
    return {"rotation": rotation, "metrics": m, "ratings": r}


def _minmax(values):
    lo, hi = min(values), max(values)
    return [0.0 if hi == lo else (v - lo) / (hi - lo) for v in values]


def score_all(entries, priorities):
    """Composite score in [0, 1], higher is better, using min-max normalisation across the
    candidates and the farmer's priority sliders as weights."""
    w = {k: max(float(priorities.get(k, 0)), 0.0) for k in DEFAULT_PRIORITIES}
    if sum(w.values()) == 0:
        w = dict(DEFAULT_PRIORITIES)
    total = sum(w.values())
    w = {k: v / total for k, v in w.items()}

    water = _minmax([e["metrics"]["water_use_mm"] for e in entries])
    nitrogen = _minmax([e["ratings"]["nitrogen"]["index"] for e in entries])
    cover = _minmax([e["ratings"]["cover"]["fraction"] for e in entries])
    risk = [(a + b) / 2 for a, b in zip(
        _minmax([e["metrics"]["shortfall_dry_mm"] for e in entries]),
        _minmax([e["metrics"]["severe_stress_days_dry"] for e in entries]))]
    for e, wa, n, c, rk in zip(entries, water, nitrogen, cover, risk):
        e["score"] = (w["water"] * (1 - wa) + w["nitrogen"] * (1 - n)
                      + w["soil_cover"] * c + w["weather_risk"] * (1 - rk))
    return w


def pick_options(entries):
    """Up to five distinct options, one per label, taking the next best when a rotation already won."""
    chosen, used = [], set()

    def take(label, key, reverse=False):
        ranked = sorted(entries, key=lambda e: (key(e) * (-1 if reverse else 1), -e["score"]))
        for e in ranked:
            k = rotations.canonical_rotation(tuple((c, None) for c, _ in e["rotation"]))
            if k not in used:
                used.add(k)
                e = dict(e, label=label)
                chosen.append(e)
                return

    take("lowest_water", lambda e: e["metrics"]["water_use_mm"])
    take("lowest_nitrogen", lambda e: e["ratings"]["nitrogen"]["index"])
    take("best_soil_cover", lambda e: e["ratings"]["cover"]["fraction"], reverse=True)
    take("lowest_dry_year_risk", lambda e: e["metrics"]["shortfall_dry_mm"])
    take("balanced", lambda e: -e["score"])
    return chosen


def compare(option, base, irrigation):
    """Plain-language comparison against the baseline, and warnings."""
    o, b = option["metrics"], base["metrics"]
    ro, rb = option["ratings"], base["ratings"]
    pct = round5(100 * o["water_use_mm"] / b["water_use_mm"]) if b["water_use_mm"] else 100
    d_short = round(o["shortfall_dry_mm"] - b["shortfall_dry_mm"])
    d_short_r = int(5 * round(d_short / 5))

    why, trade = [], []
    if pct < 100:
        why.append(f"Crop water use is about {pct}% of your rotation's ({round(o['water_use_mm'])} vs {round(b['water_use_mm'])} mm a season).")
    elif pct > 100:
        trade.append(f"Crop water use is about {pct}% of your rotation's ({round(o['water_use_mm'])} vs {round(b['water_use_mm'])} mm a season).")
    else:
        why.append("Crop water use is about the same as your rotation's.")

    risk_word = "water you would need to supply" if irrigation else "water the crop would miss"
    if d_short_r < 0:
        why.append(f"In a dry year (about 1 in 10) it would miss about {abs(d_short_r)} mm less {('irrigation' if irrigation else 'water')}.")
    elif d_short_r > 0:
        trade.append(f"In a dry year (about 1 in 10) it would miss about {d_short_r} mm more {('irrigation' if irrigation else 'water')}.")

    n_o, n_b = ro["nitrogen"], rb["nitrogen"]
    if n_o["index"] < n_b["index"] - 0.05:
        credit = ", ".join(CROP_NAMES[c] for c in dict.fromkeys(n_o["legume_credit_crops"]))
        why.append(f"Nitrogen demand is lower: {n_o['index']} vs your {n_b['index']} (1 = low, 3 = high)"
                   + (f", because a legume comes before {credit}." if credit else "."))
    elif n_o["index"] > n_b["index"] + 0.05:
        trade.append(f"Nitrogen demand is higher: {n_o['index']} vs your {n_b['index']} (1 = low, 3 = high).")

    c_o, c_b = ro["cover"], rb["cover"]
    if c_o["fraction"] > c_b["fraction"] + 0.02:
        why.append(f"Soil is covered for more of the year: {c_o['label']} cover vs your {c_b['label']}.")
    elif c_o["fraction"] < c_b["fraction"] - 0.02:
        trade.append(f"Soil is covered for less of the year: {c_o['label']} cover vs your {c_b['label']}.")

    p_o, p_b = ro["pest_break"], rb["pest_break"]
    if p_o["label"] != p_b["label"]:
        (why if ["poor", "fair", "good"].index(p_o["label"]) > ["poor", "fair", "good"].index(p_b["label"]) else trade).append(
            f"Pest and disease break: {p_o['label']} (yours: {p_b['label']}).")

    warnings = list(ro["timing_notes"]) + p_o["violations"]
    covers = [cv for _, cv in option["rotation"] if cv]
    if covers:
        warnings.append("Cover-crop water use is not modelled (no reliable library values), so water figures cover the main crops only.")
        trade.append("Cover crops add seeding and termination work.")
    if (not irrigation and o["dry_shortfall_share"] > SEVERE_SHORTFALL_FRACTION
            and o["dry_shortfall_share"] > b["dry_shortfall_share"] + 0.02):
        warnings.append("Larger dry-year water shortfall than your rotation, and no irrigation.")
    if ro["timing_notes"]:
        trade.append("Extra harvest and planting workload at the fall changeover.")
    return {
        "vs_baseline": {"water_use_pct": pct, "dry_year_shortfall_change_mm": d_short_r,
                        "nitrogen_change": round(n_o["index"] - n_b["index"], 2),
                        "cover_change": round(c_o["fraction"] - c_b["fraction"], 2)},
        "why": " ".join(why) if why else "Similar to your current rotation on the criteria tracked here.",
        "tradeoffs": trade, "warnings": list(dict.fromkeys(warnings)),
    }


def _confidence(entry, crops):
    quality = {crops[c]["data_quality"] for c, _ in entry["rotation"]}
    water = "moderate" if quality == {"well_supported"} else "low"
    has_cover = any(cv for _, cv in entry["rotation"])
    return {
        "water": f"{water} confidence" + ("; cover-crop water not modelled" if has_cover else ""),
        "dry_year_risk": "moderate confidence" if entry["metrics"]["n_years"] >= 30 else "low confidence",
        "nitrogen": "qualitative only (rule-based)",
        "soil_cover": "qualitative only (assumed crop calendars)",
        "pest_break": "qualitative only (rule-based)",
    }


def _present(entry, crops, extra=None):
    m, r = entry["metrics"], entry["ratings"]
    out = {
        "name": _name(entry["rotation"]),
        "rotation": _describe(entry["rotation"]),
        "metrics": {
            "water_use_mm": round(m["water_use_mm"]), "dry_year_shortfall_mm": round(m["shortfall_dry_mm"]),
            "typical_year_shortfall_mm": round(m["shortfall_typical_mm"]),
            "severe_stress_days_typical": round(m["severe_stress_days_typical"], 1),
            "severe_stress_days_dry": round(m["severe_stress_days_dry"], 1),
            "hot_days_30c_typical": round(m["hot_days_30c_typical"], 1),
            "survived_years": m["survived_years"], "years_simulated": m["n_years"],
            "by_crop": m["by_crop"],
        },
        "ratings": {"nitrogen": r["nitrogen"], "soil_cover": r["cover"], "pest_break": r["pest_break"]},
        "confidence": _confidence(entry, crops),
    }
    out.update(extra or {})
    return out


def recommend(request):
    crops, soils, rules = _reference()
    soils = {k: v for k, v in soils.items() if not k.startswith("_")}
    try:
        lat, lon = float(request["lat"]), float(request["lon"])
    except (KeyError, TypeError, ValueError):
        raise InputError("lat and lon are required numbers")
    soil = request.get("soil", "loam")
    if soil not in soils:
        raise InputError(f"soil must be one of {', '.join(soils)}")
    anchor = snap(lat, lon)
    irrigation = bool(request.get("irrigation", False))
    equipment = request.get("equipment")
    warnings = []

    current = list(request.get("current_rotation") or [])
    default_used = not current
    if default_used:
        current = list(DEFAULT_ROTATION)
        warnings.append("No current rotation entered: corn-soybean is used as a default baseline.")
    unknown = [c for c in current if c not in rotations.MAIN_CROPS]
    if unknown:
        raise InputError(f"Cannot model {', '.join(unknown)} as a main crop; supported: {', '.join(rotations.MAIN_CROPS)}")
    if len(current) > 4:
        raise InputError("Current rotation can have at most 4 years")
    baseline_rot = tuple((c, None) for c in current)

    known = set(rotations.MAIN_CROPS) | set(rotations.COVER_CROPS)
    must = [c for c in request.get("must_include", []) if c in known]
    avoid = [c for c in request.get("avoid", []) if c in known]
    for c in request.get("must_include", []):
        if c not in known:
            warnings.append(f"No data for {c}: it cannot be modelled, so it was not built into the options. "
                            "Rotations that include it need local review.")
    if len(current) == 1 and current[0] not in must:
        must.append(current[0])
        warnings.append(f"You entered one crop ({CROP_NAMES[current[0]]}), so options all include it.")
    overlap = set(must) & set(avoid)
    if overlap:
        raise InputError(f"Cannot both include and avoid: {', '.join(sorted(overlap))}")

    base = build_entry(anchor["id"], soil, baseline_rot)
    if base is None:
        raise InputError("Not enough weather data to evaluate this rotation here")

    cands = rotations.filter_candidates(rotations.all_candidates(rules), crops, must, avoid, equipment)
    base_key = rotations.canonical_rotation(baseline_rot)
    allow_repeat = _has_repeat(baseline_rot)
    entries = [e for e in (build_entry(anchor["id"], soil, r) for r in cands)
               if e and rotations.canonical_rotation(e["rotation"]) != base_key
               and (allow_repeat or not _has_repeat(e["rotation"]))]
    if not entries:
        raise InputError("No rotation meets all of your constraints. Try relaxing them.")

    weights = score_all(entries + [base], request.get("priorities") or DEFAULT_PRIORITIES)
    options = []
    for opt in pick_options(entries):
        cmp = compare(opt, base, irrigation)
        options.append(_present(opt, crops, {
            "label": opt["label"], "label_text": LABEL_TEXT[opt["label"]], "score": round(opt["score"], 2), **cmp}))

    if not irrigation and base["metrics"]["dry_shortfall_share"] > SEVERE_SHORTFALL_FRACTION:
        warnings.append("Without irrigation, dry years leave a large water shortfall at this location for your own rotation too.")
    chart_crops = list(dict.fromkeys(c for c, _ in baseline_rot))
    return {
        "disclaimer": "Educational decision support, not agronomic advice. Results are relative comparisons, not field predictions.",
        "anchor": anchor,
        "inputs_used": {"soil": soil, "irrigation": irrigation, "tile_drainage": bool(request.get("tile_drainage", False)),
                        "equipment": equipment, "must_include": must, "avoid": avoid,
                        "priority_weights": {k: round(v, 2) for k, v in weights.items()}, "default_baseline": default_used},
        "baseline": _present(base, crops, {"label": "your_rotation", "label_text": "Your rotation (100%)"}),
        "options": options,
        "charts": {"typical_vs_dry_by_crop": {c: base["metrics"]["by_crop"][c] for c in chart_crops}},
        "sources": SOURCES,
        "warnings": warnings + ["Tile drainage, water tables and runoff are not modelled.",
                                "Percentages are rounded to the nearest 5%."],
    }
