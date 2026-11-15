"""Precompute per-year crop metrics for every anchor x soil x crop.

Output (committed, small):
  backend/data/processed/crop_year_metrics.csv   one row per anchor/soil/crop/year
  backend/data/processed/anchor_summary.json     map-ready stats per anchor

Run from the repo root:  python backend/data_scripts/build_metrics.py
"""
import json
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from engine import et0, water_balance as wb
from engine.weather import DATA_DIR, complete_years, load_anchors, load_reference, load_weather

MAIN_CROPS = ["corn", "soybean", "winter_wheat"]   # crops with enough library data to simulate
YEARS = range(1981, 2025)


def main():
    anchors, crops, soils = load_anchors(), load_reference("crops"), load_reference("soil_texture")
    soils = {k: v for k, v in soils.items() if not k.startswith("_")}
    frames, summary = [], {}

    for anchor, pos in anchors.items():
        weather = load_weather(anchor)
        frame = weather[["tmax_c", "precip_mm"]].join(et0.et0_frame(weather, pos["lat"]))
        for soil_id, soil in soils.items():
            for crop_id in MAIN_CROPS:
                m = wb.simulate_years(frame, crops[crop_id], soil, YEARS)
                if m.empty:
                    continue
                m = m.reset_index()
                m.insert(0, "crop", crop_id)
                m.insert(0, "soil", soil_id)
                m.insert(0, "anchor", anchor)
                frames.append(m)

        # map summary: corn on loam as the reference case
        ref = wb.simulate_years(frame, crops["corn"], soils["loam"], YEARS)
        s = wb.summarize(ref)
        may_sep = weather[(weather.index.month >= 5) & (weather.index.month <= 9)]
        years_ok = complete_years(weather)
        summary[anchor] = {
            "lat": pos["lat"], "lon": pos["lon"],
            "reference_case": "corn on loam",
            "dry_year_shortfall_mm": round(s["shortfall_mm_dry"]),
            "typical_shortfall_mm": round(s["shortfall_mm_typical"]),
            "survived_years": s["survived_years"], "n_years": s["n_years"],
            "may_sep_rain_mm": round(float(may_sep["precip_mm"].groupby(may_sep.index.year).sum().mean())),
            "hot_days_30c_per_year": round(float((weather["tmax_c"] >= 30).groupby(weather.index.year).sum().mean()), 1),
            "years_with_complete_data": len(years_ok),
            "source_type": "Simulated from NASA-derived (POWER) weather",
        }
        print(f"{anchor:13} done")

    out_dir = DATA_DIR / "processed"
    out_dir.mkdir(parents=True, exist_ok=True)
    table = pd.concat(frames, ignore_index=True)
    table.to_csv(out_dir / "crop_year_metrics.csv", index=False, float_format="%.3f")
    (out_dir / "anchor_summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(f"\n{len(table)} rows -> {out_dir / 'crop_year_metrics.csv'}")


if __name__ == "__main__":
    main()
