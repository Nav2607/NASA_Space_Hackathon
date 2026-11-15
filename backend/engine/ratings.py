"""Rule-based ratings for a rotation: nitrogen demand, soil cover, pest break, timing.

A rotation is a tuple of years; each year is (main_crop, cover_crop_or_None), e.g.
(("corn", "cereal_rye"), ("soybean", None), ("winter_wheat", "red_clover")).
The cycle repeats, so the 'previous year' of year 0 is the last year.

All ratings here are qualitative and rule-based. Calendar-derived numbers and thresholds that
are not tied to a published source are marked ASSUMED and must be shown as 'Assumed'.
"""
import datetime as dt

N_LEVEL = {"low": 1, "medium": 2, "high": 3}
N_LABEL_CUTS = (1.67, 2.34)           # ASSUMED cut-offs between low / medium / high
COVER_LABEL_CUTS = (0.45, 0.65)       # ASSUMED cut-offs between low / medium / high
RYE_COVER_DAYS = 180                  # ASSUMED: late summer/fall seeding to spring termination
CLOVER_COVER_DAYS = 280               # ASSUMED: underseeded clover, after wheat harvest to next spring


def _doy(md):
    return dt.date(2001, int(md[:2]), int(md[3:])).timetuple().tm_yday


def _mid(window):
    return (_doy(window[0]) + _doy(window[1])) / 2


def main_cover_days(crop):
    """Days of living cover for a main crop, from the midpoints of its planting and harvest windows."""
    plant, harvest = _mid(crop["plant_window"]), _mid(crop["harvest_window"])
    return (365 - plant + harvest) if plant > harvest else (harvest - plant)   # fall-planted wraps the year


def _label(value, cuts):
    return "low" if value < cuts[0] else ("medium" if value < cuts[1] else "high")


def nitrogen_rating(rotation, crops):
    """Mean ordinal demand (high 3, medium 2, low 1); no uncited nitrogen credits."""
    levels, credits = [], []
    for i, (crop, _) in enumerate(rotation):
        level = N_LEVEL[crops[crop]["n_base_class"]]
        # The existing blanket legume-credit rule has status needs_citation.
        # Do not apply an unsupported nitrogen reduction to scored alternatives.
        levels.append(level)
    index = sum(levels) / len(levels)
    return {"index": round(index, 2), "label": _label(index, N_LABEL_CUTS),
            "legume_credit_crops": credits, "source_type": "Rule-based ordinal indicator",
            "note": "No nitrogen credits applied: predecessor-specific citations are incomplete"}


def cover_rating(rotation, crops):
    """Share of the year with living cover, averaged over the cycle (main crop + cover crop days)."""
    days = 0
    for crop, cover in rotation:
        days += min(365, main_cover_days(crops[crop])
                    + {"cereal_rye": RYE_COVER_DAYS, "red_clover": CLOVER_COVER_DAYS}.get(cover, 0))
    fraction = min(1.0, days / (365 * len(rotation)))
    return {"fraction": round(fraction, 2), "label": _label(fraction, COVER_LABEL_CUTS)}


def pest_break_rating(rotation, crops, rules):
    """Counts repeat-too-soon violations (min_gap_years, disallowed successions); good / fair / poor."""
    n = len(rotation)
    violations, benefits = [], 0
    gap_rules, pest = rules["min_gap_years"], rules["pest_break"]
    for i, (crop, _) in enumerate(rotation):
        gap = next(k for k in range(1, n + 1) if rotation[(i - k) % n][0] == crop)
        rule = gap_rules.get(crop)
        if rule and ((gap == 1 and rule["flag_if_repeated"]) or gap <= rule["value"]):
            violations.append(f"{crop} returns after {gap} year{'s' if gap > 1 else ''}: {rule['note']}")
        prev = rotation[i - 1][0]
        if pest.get(crop, {}).get(f"after_{prev}") == "better":
            benefits += 1
        for d in rules["disallowed_successions"]:
            if d["from"] == prev and d["to"] == crop:
                violations.append(f"{prev} followed by {crop}: {d['reason']}")
    unique = list(dict.fromkeys(violations))
    return {"label": "good" if not unique else ("fair" if len(unique) == 1 else "poor"),
            "violations": unique, "break_years": benefits}


def timing_notes(rotation, crops):
    """Tight-timing flags: a fall-planted crop after a harvest that runs past its planting window,
    and cover crop seeded late after corn."""
    notes = []
    for i, (crop, cover) in enumerate(rotation):
        prev = rotation[i - 1][0]
        plant_win, prev_harvest = crops[crop]["plant_window"], crops[prev]["harvest_window"]
        if _doy(plant_win[0]) > _doy("08-01") and _mid(prev_harvest) > _doy(plant_win[1]):
            notes.append(f"{crop.replace('_', ' ')} after {prev.replace('_', ' ')}: harvest usually runs past the planting dates")
        if cover == "cereal_rye" and crop == "corn":
            notes.append("cereal rye after corn is seeded late (corn harvest runs into November), so growth may be limited")
    return notes


def rate(rotation, crops, rules):
    return {
        "nitrogen": nitrogen_rating(rotation, crops),
        "cover": cover_rating(rotation, crops),
        "pest_break": pest_break_rating(rotation, crops, rules),
        "timing_notes": timing_notes(rotation, crops),
    }
