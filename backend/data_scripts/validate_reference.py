"""Validate the hand-entered reference tables.

Errors (exit code 1): broken JSON, unknown source ids, values with no source,
'assumed' fields that do not exist. Gaps (null values) are reported but are not errors,
because unknown values are allowed by design.
"""
import json
import sys
from pathlib import Path

REF = Path(__file__).resolve().parents[1] / "data" / "reference"
errors: list[str] = []
gaps: list[str] = []


def load(name):
    try:
        return json.loads((REF / name).read_text(encoding="utf-8"))
    except (OSError, ValueError) as err:
        errors.append(f"{name}: cannot read ({err})")
        return {}


def flatten_nulls(prefix, value):
    if value is None:
        gaps.append(prefix)
    elif isinstance(value, dict):
        for k, v in value.items():
            flatten_nulls(f"{prefix}.{k}", v)
    elif isinstance(value, list):
        for i, v in enumerate(value):
            if v is None:
                gaps.append(f"{prefix}[{i}]")


def has_number(value):
    if isinstance(value, bool):
        return False
    if isinstance(value, (int, float)):
        return True
    if isinstance(value, dict):
        return any(has_number(v) for v in value.values())
    if isinstance(value, list):
        return any(has_number(v) for v in value)
    return False


sources = load("sources.json")
crops = load("crops.json")
soils = load("soil_texture.json")
rules = load("rotation_rules.json")

NUMERIC_CROP_FIELDS = ["kc", "stage_days", "root_depth_m", "depletion_fraction_p", "heat_threshold_c"]

for cid, crop in crops.items():
    if cid.startswith("_"):
        continue
    for sid in crop.get("sources", []):
        if sid not in sources:
            errors.append(f"crops.{cid}: unknown source '{sid}'")
    if crop.get("data_quality") not in {"well_supported", "limited", "none"}:
        errors.append(f"crops.{cid}: bad data_quality")
    if any(has_number(crop.get(f)) for f in NUMERIC_CROP_FIELDS) and not crop.get("sources"):
        errors.append(f"crops.{cid}: has numeric values but no sources")
    for field in crop.get("assumed", []):
        if field not in crop:
            errors.append(f"crops.{cid}: assumed field '{field}' does not exist")
    for f in NUMERIC_CROP_FIELDS:
        flatten_nulls(f"crops.{cid}.{f}", crop.get(f))

for sid, soil in soils.items():
    if sid.startswith("_"):
        continue
    if soil.get("available_water_mm_per_m") is not None and not soil.get("sources"):
        errors.append(f"soil.{sid}: value without a source")
    for s in soil.get("sources", []):
        if s not in sources:
            errors.append(f"soil.{sid}: unknown source '{s}'")
    flatten_nulls(f"soil.{sid}.available_water_mm_per_m", soil.get("available_water_mm_per_m"))

crop_ids = {c for c in crops if not c.startswith("_")}
for cid in rules.get("min_gap_years", {}):
    if cid not in crop_ids:
        errors.append(f"rotation_rules.min_gap_years: unknown crop '{cid}'")

print(f"Crops: {len(crop_ids)}   Soils: {len([s for s in soils if not s.startswith('_')])}")
print(f"\nGaps (null values, shown as 'no data' in the app): {len(gaps)}")
for g in gaps:
    print(f"  - {g}")
print(f"\nErrors: {len(errors)}")
for e in errors:
    print(f"  ! {e}")
sys.exit(1 if errors else 0)
