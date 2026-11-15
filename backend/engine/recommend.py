"""Constraint-preserving comparisons of continuous rotations; NASA calls stay offline."""
import math
from functools import lru_cache

import numpy as np

from . import ratings, rotations, climate_future
from .rotation_simulation import simulate_rotation, CalendarError, ASSUMPTIONS, ET0_METHOD
from .weather import load_anchors, load_reference, load_weather

MAX_SNAP_KM = 150.0
DEFAULT_ROTATION = ["corn", "soybean"]
DEFAULT_PRIORITIES = {"water": .25, "nitrogen": .25, "soil_cover": .25, "weather_risk": .25}
CROP_NAMES = {"corn": "corn", "soybean": "soybean", "winter_wheat": "winter wheat",
              "red_clover": "red clover", "cereal_rye": "cereal rye"}
LABEL_TEXT = {"lowest_water": "Lowest potential water demand", "lowest_nitrogen": "Lowest ordinal nitrogen indicator",
              "best_soil_cover": "Most calendar-derived living cover", "lowest_dry_year_risk": "Lowest p90 unmet demand",
              "balanced": "Highest weighted score", "additional_alternative": "Additional feasible alternative"}
SOURCES = {"water_use": "Modeled potential ETc, not measured water consumption",
           "actual_et": "Modeled water-limited actual ET", "dry_year_shortfall": "Modeled unmet demand",
           "stress_days": "Modeled depletion threshold", "weather": "NASA-derived POWER; precipitation fallback",
           "future": "NEX model-specific monthly change factors applied to historical POWER daily sequences; not forecasts",
           "nitrogen": "Rule-based ordinal indicator; no uncited predecessor credit",
           "soil_cover": "Rule-based crop-calendar indicator, not erosion protection measurements"}


class InputError(ValueError):
    pass


def round5(x):
    return int(5 * round(x / 5))


def haversine_km(lat1, lon1, lat2, lon2):
    p1, p2 = math.radians(lat1), math.radians(lat2)
    a = math.sin((p2-p1)/2)**2 + math.cos(p1)*math.cos(p2)*math.sin(math.radians(lon2-lon1)/2)**2
    return 12742 * math.asin(math.sqrt(min(1, max(0, a))))


def snap(lat, lon):
    if not math.isfinite(lat) or not math.isfinite(lon) or not 41 <= lat <= 47 or not -84 <= lon <= -74:
        raise InputError("Coordinates must be finite and within the Southern Ontario supported region")
    anchors = load_anchors()
    if not anchors or any(not (-90 <= p['lat'] <= 90 and -180 <= p['lon'] <= 180) for p in anchors.values()):
        raise InputError("Invalid anchor coordinates")
    best = min(anchors, key=lambda a: haversine_km(lat, lon, anchors[a]['lat'], anchors[a]['lon']))
    dist = haversine_km(lat, lon, anchors[best]['lat'], anchors[best]['lon'])
    if dist > MAX_SNAP_KM:
        raise InputError("Point is outside supported anchor coverage")
    return {"id": best, **anchors[best], "distance_km": round(dist, 1)}


@lru_cache(maxsize=1)
def _reference():
    return load_reference("crops"), load_reference("soil_texture"), load_reference("rotation_rules")


@lru_cache(maxsize=512)
def _run(anchor, soil, rotation, first, last, model=None, scenario="ssp245"):
    crops, soils, _ = _reference()
    weather = load_weather(anchor)
    if model is not None:
        pos = load_anchors()[anchor]
        doc = climate_future.deltas_at(pos['lat'], pos['lon'], scenario, "2031_2050")
        weather = climate_future.apply_deltas(weather, doc['models'][model])
    return simulate_rotation(weather, load_anchors()[anchor]['lat'], rotation, crops, soils[soil], first, last)


def _historical(anchor, soil, rotation, first, last):
    run = _run(anchor, soil, rotation, first, last)
    return {"status": "available", "period": {"start": first, "end": last},
            "source_type": "Modeled from NASA-derived POWER", **run}


def _future(anchor, soil, rotation, scenario="ssp245"):
    """Never use the ensemble climate inputs. Simulate each named model first."""
    try:
        pos = load_anchors()[anchor]
        doc = climate_future.deltas_at(pos['lat'], pos['lon'], scenario, "2031_2050")
        first, last = doc['baseline_period']['start'], doc['baseline_period']['end']
        if last - first != 19:
            raise ValueError("Future delta realization requires a matched 20-year POWER reference period")
        runs = {model: _run(anchor, soil, rotation, first, last, model, scenario) for model in doc['models']}
        keys = next(iter(runs.values()))['metrics']
        metrics = {key: float(np.median([r['metrics'][key] for r in runs.values()])) for key in keys}
        ranges = {key: {"min": min(r['metrics'][key] for r in runs.values()),
                        "max": max(r['metrics'][key] for r in runs.values())} for key in keys}
        return {"status": "available", "period": {"start": 2031, "end": 2050}, "scenario": scenario,
                "dataset": doc.get('dataset'), "dataset_version": doc.get('version'),
                "member": doc.get('member'), "source_url": doc.get('source_url'),
                "source_type": "Modeled outcomes under NEX-derived monthly change factors",
                "weather_sequence_period": {"start": first, "end": last},
                "climate_model_reference_period": doc['baseline_period'], "grid_cell": doc['cell'],
                "method": doc['method'], "et0_method": ET0_METHOD,
                "note": "Historical dates and event sequencing retained; this is a future-climate sensitivity realization, not a daily forecast. Same-model reference change factors do not remove all cross-product differences.",
                "metrics": metrics, "model_range": ranges, "models": runs, "model_count": len(runs),
                "uncertainty_note": "Min/max describe model spread, not probabilities or confidence intervals." if len(runs)>1 else "Only one model available; no inter-model uncertainty estimate."}
    except (FileNotFoundError, ValueError, KeyError, OSError) as err:
        return {"status": "insufficient_data", "period": {"start": 2031, "end": 2050},
                "scenario": scenario, "reason": str(err), "metrics": None, "models": {}}


def evaluate(anchor, soil, rotation):
    """Compatibility helper; independent per-crop precomputed CSVs are not used."""
    try:
        run = _run(anchor, soil, tuple(rotation), 2005, 2024)
    except (ValueError, KeyError, OSError):
        return None
    m = dict(run['metrics'])
    return {**m, "n_years": run['n_years'], "phase_count": len(rotation), "by_crop": {}}


def build_entry(anchor, soil, rotation):
    run = _historical(anchor, soil, rotation, 2005, 2024)
    crops, _, rules = _reference()
    r = ratings.rate(rotation, crops, rules)
    # A scored soil-cover indicator uses actual modeled occupancy, not added cover days.
    fraction = run['metrics']['living_cover_fraction']
    r['cover'] = {'fraction': fraction, 'label': ratings._label(fraction, ratings.COVER_LABEL_CUTS)}
    r['cover']['note'] = "Calendar-derived living cover only; no cover variants or residue erosion model"
    return {"rotation": rotation, "metrics": dict(run['metrics']), "ratings": r, "historical_run": run,
            "metrics_period": "historical_2005_2024"}


def _minmax(values):
    lo, hi = min(values), max(values)
    return [0.0 if hi == lo else (v-lo)/(hi-lo) for v in values]


def score_all(entries, priorities):
    if set(priorities) - set(DEFAULT_PRIORITIES):
        raise InputError("Unknown priority")
    try:
        weights = {k: float(priorities.get(k, 0)) for k in DEFAULT_PRIORITIES}
    except (TypeError, ValueError):
        raise InputError("Priorities must be numeric")
    if any(not math.isfinite(v) or not 0 <= v <= 1 for v in weights.values()):
        raise InputError("Priorities must be finite within [0,1]")
    if not sum(weights.values()):
        weights = dict(DEFAULT_PRIORITIES)
    total = sum(weights.values())
    weights = {k: v/total for k, v in weights.items()}
    normalized = {key: _minmax([e['metrics'][key] for e in entries]) for key in
                  ['water_use_mm', 'shortfall_dry_mm', 'critical_stress_days', 'heat_stress_days']}
    nitrogen = _minmax([e['ratings']['nitrogen']['index'] for e in entries])
    cover = _minmax([e['ratings']['cover']['fraction'] for e in entries])
    for i, e in enumerate(entries):
        water = (normalized['water_use_mm'][i] + normalized['shortfall_dry_mm'][i])/2
        risk = (normalized['shortfall_dry_mm'][i] + normalized['critical_stress_days'][i] + normalized['heat_stress_days'][i])/3
        e['score'] = weights['water']*(1-water) + weights['weather_risk']*(1-risk) + weights['nitrogen']*(1-nitrogen[i]) + weights['soil_cover']*cover[i]
    return weights


def pick_options(entries):
    if not entries:
        return []
    chosen, used = [], set()
    for label, key in [('lowest_water', lambda e: e['metrics']['water_use_mm']),
                       ('lowest_nitrogen', lambda e: e['ratings']['nitrogen']['index']),
                       ('best_soil_cover', lambda e: -e['ratings']['cover']['fraction']),
                       ('lowest_dry_year_risk', lambda e: e['metrics']['shortfall_dry_mm']),
                       ('balanced', lambda e: -e['score'])]:
        e = min(entries, key=lambda e: (key(e), -e['score']))
        identity = rotations.canonical_rotation(e['rotation'])
        if identity not in used:
            used.add(identity)
            chosen.append(dict(e, label=label, labels=[label]))
        else:
            next(item for item in chosen if rotations.canonical_rotation(item['rotation']) == identity)['labels'].append(label)
    for e in sorted(entries, key=lambda e: -e['score']):
        identity = rotations.canonical_rotation(e['rotation'])
        if len(chosen) >= 5:
            break
        if identity not in used:
            used.add(identity)
            chosen.append(dict(e, label='additional_alternative', labels=['additional_alternative']))
    return chosen


def _name(rotation):
    return ' → '.join(CROP_NAMES[c] + (f" + {CROP_NAMES[cover]}" if cover else '') for c, cover in rotation)


def _present(entry, default=False):
    m = entry['metrics']
    metrics = {"water_use_mm": round(m['water_use_mm'], 2),
               "potential_demand_mm": round(m['water_use_mm'], 2), "actual_et_mm": round(m['actual_et_mm'], 2),
               "dry_year_shortfall_mm": round(m['shortfall_dry_mm'], 2),
               "typical_year_shortfall_mm": round(m['shortfall_typical_mm'], 2),
               "threshold_stress_days_typical": round(m['stress_days'], 2),
               "critical_stress_days_typical": round(m['critical_stress_days'], 2),
               "unmet_demand_days_typical": round(m['unmet_demand_days'], 2),
               "heat_stress_days_typical": round(m['heat_stress_days'], 2),
               "years_simulated": 20, "by_crop": {}}
    return {"name": _name(entry['rotation']), "rotation": [{"crop": c, "cover_crop": cover} for c, cover in entry['rotation']],
            "metrics": metrics, "ratings": {"nitrogen": entry['ratings']['nitrogen'], "soil_cover": entry['ratings']['cover'],
                                            "pest_break": entry['ratings']['pest_break']},
            "confidence": {"water": "limited: regional climate, fixed soil depth and calendar assumptions",
                           "nitrogen": "ordinal, rule-based; no verified credit", "soil_cover": "calendar-based only"},
            "default_baseline": default, "metrics_period": entry['metrics_period']}


def _time_machine(anchor, soil, rotation, future):
    return {"historical_2005_2014": _historical(anchor, soil, rotation, 2005, 2014),
            "historical_2015_2024": _historical(anchor, soil, rotation, 2015, 2024),
            "future_2031_2050": future}


def recommend(request):
    crops, soils, rules = _reference()
    try:
        anchor = snap(float(request['lat']), float(request['lon']))
    except (TypeError, KeyError, ValueError) as err:
        raise InputError(f"Invalid location: {err}")
    soil = request.get('soil', 'loam')
    if soil not in soils or soil.startswith('_'):
        raise InputError("Unsupported soil texture")
    current = request.get('current_rotation') or list(DEFAULT_ROTATION)
    default = not request.get('current_rotation')
    if not isinstance(current, list) or not 1 <= len(current) <= 4 or any(not isinstance(c,str) for c in current):
        raise InputError("Baseline requires 1–4 crop IDs")
    if any(c not in rotations.MAIN_CROPS for c in current):
        return {"status": "insufficient_data", "reason": "Unsupported baseline crop demand/calendar inputs",
                "anchor": anchor, "baseline": {"rotation": [{"crop": c,"cover_crop": None} for c in current], "metrics": None},
                "options": [], "warnings": list(ASSUMPTIONS)}
    rotation = tuple((c, None) for c in current)
    known = set(rotations.MAIN_CROPS + rotations.COVER_CROPS)
    must, avoid = request.get('must_include', []), request.get('avoid', [])
    if not isinstance(must, list) or not isinstance(avoid, list) or any(not isinstance(c, str) for c in must+avoid):
        raise InputError("Crop constraints must be lists of IDs")
    if set(must) & set(avoid):
        raise InputError("Cannot both require and avoid a crop")
    if set(avoid)-known:
        raise InputError("Unknown avoid-grow crop IDs")
    equipment = request.get('equipment')
    if equipment is not None and (not isinstance(equipment, list) or set(equipment)-{'planter','combine','grain_drill'}):
        raise InputError("Unknown equipment IDs")
    if request.get('allow_cover_crops', False) not in (False, True):
        raise InputError("allow_cover_crops must be boolean")
    warnings = list(ASSUMPTIONS)
    if default:
        warnings.append("No rotation supplied; default corn–soybean baseline used")
    try:
        base = build_entry(anchor['id'], soil, rotation)
    except (ValueError, KeyError, OSError) as err:
        return {"status": "insufficient_data", "reason": str(err), "anchor": anchor,
                "baseline": {"rotation": [{"crop": c, "cover_crop": None} for c in current], "metrics": None},
                "options": [], "warnings": warnings}
    base_future = _future(anchor['id'], soil, rotation)
    scoring = request.get('climate_period', 'historical')
    if scoring not in {'historical', 'future'}:
        raise InputError("climate_period must be historical or future")
    future_available = base_future['status'] == 'available'
    if scoring == 'future' and future_available:
        base['metrics'] = dict(base_future['metrics'])
        base['metrics_period'] = 'future_2031_2050'
        base['ratings']['cover']['fraction'] = base_future['metrics']['living_cover_fraction']
    insufficient = []
    if set(must)-set(rotations.MAIN_CROPS):
        insufficient.append("Required crop(s) unsupported for scored water comparisons: " + ', '.join(sorted(set(must)-set(rotations.MAIN_CROPS))) + "; mandatory constraints were retained")
    if scoring == 'future' and not future_available:
        insufficient.append("Agreed future climate data unavailable; no historical scores substituted for future scores")
    cands = [] if insufficient else rotations.filter_candidates(rotations.all_candidates(rules), crops, must, avoid, equipment)
    entries = []
    rejected = []
    for candidate in cands:
        if rotations.canonical_rotation(candidate) == rotations.canonical_rotation(rotation):
            continue
        try:
            entry = build_entry(anchor['id'], soil, candidate)
            future = _future(anchor['id'], soil, candidate)
            if scoring == 'future':
                if future['status'] != 'available':
                    rejected.append(future['reason'])
                    continue
                entry['metrics'] = dict(future['metrics'])
                entry['metrics_period'] = 'future_2031_2050'
                entry['ratings']['cover']['fraction'] = future['metrics']['living_cover_fraction']
            entry['future'] = future
            entries.append(entry)
        except (ValueError, KeyError, OSError) as err:
            rejected.append(str(err))
    weights = score_all(entries+[base], request.get('priorities') or DEFAULT_PRIORITIES)
    options = []
    for entry in pick_options(entries):
        o = _present(entry)
        b, m = base['metrics'], entry['metrics']
        pct = round5(100*m['water_use_mm']/b['water_use_mm']) if b['water_use_mm'] > 0 else None
        o.update({"label": entry['label'], "labels": entry['labels'], "label_text": LABEL_TEXT[entry['label']],
                  "score": round(entry['score'], 4),
                  "vs_baseline": {"water_use_pct": pct,
                                  "dry_year_shortfall_change_mm": round(m['shortfall_dry_mm']-b['shortfall_dry_mm'], 2),
                                  "nitrogen_change": round(entry['ratings']['nitrogen']['index']-base['ratings']['nitrogen']['index'], 2),
                                  "cover_change": round(entry['ratings']['cover']['fraction']-base['ratings']['cover']['fraction'], 2)},
                  "why": "Feasible under the supplied mandatory constraints; compare potential demand and unmet demand together.",
                  "tradeoffs": ["Ordinal agricultural indicators and simplified water balance do not predict yield or measured savings."],
                  "warnings": entry['ratings']['timing_notes'] + entry['ratings']['pest_break']['violations'],
                  "time_machine": _time_machine(anchor['id'], soil, entry['rotation'], entry['future'])})
        options.append(o)
    if len(entries) < 3:
        insufficient.append(f"Only {len(entries)} feasible alternatives; constraints were not relaxed")
    if not future_available:
        warnings.append("2031–2050 climate run unavailable: " + base_future['reason'])
    warnings += base['ratings']['pest_break']['violations'] + base['ratings']['timing_notes']
    return {"status": "insufficient_feasible_alternatives" if insufficient else "ok",
            "reason": '; '.join(insufficient) or None, "feasible_alternative_count": len(entries),
            "disclaimer": "Decision support, not agronomic advice. No yield, survival or field validation claims.",
            "anchor": anchor, "baseline": _present(base, default), "options": options,
            "scoring_period": 'future_2031_2050' if scoring == 'future' else 'historical_2005_2024',
            "scores_available": scoring != 'future' or future_available,
            "inputs_used": {"soil": soil, "must_include": list(must), "avoid": list(avoid), "equipment": equipment,
                            "irrigation": bool(request.get('irrigation', False)), "default_baseline": default,
                            "tile_drainage": bool(request.get('tile_drainage', False)),
                            "simulation_mode": "rainfed; irrigation and tile drainage are context only",
                            "priority_weights": weights},
            "time_machine": _time_machine(anchor['id'], soil, rotation, base_future),
            "charts": {"typical_vs_dry_by_crop": {}}, "sources": SOURCES, "warnings": warnings,
            "rejected_alternatives": sorted(set(rejected))}
