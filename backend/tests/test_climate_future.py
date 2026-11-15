"""Regression checks for the retained 2041–2060 cache; it is not the MVP future period."""
import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from engine import climate_future as cf
from engine.weather import load_anchors, load_weather

pytestmark = pytest.mark.skipif(not cf.available_files(), reason="run data_scripts/extract_nex_region.py first")


def test_every_anchor_has_projected_deltas():
    for name, p in load_anchors().items():
        d = cf.deltas_at(p["lat"], p["lon"], period="2041_2060")
        assert d["cell"]["distance_deg"] <= 0.2, name           # snapped to a cell within ~one grid step
        for var in cf.VARIABLES:
            assert len(d["median"][var]) == 12 and None not in d["median"][var], (name, var)


def test_projections_are_plausible_warming_not_nonsense():
    d = cf.deltas_at(43.55, -80.25, period="2041_2060")
    warm = np.array(d["median"]["tmax_c_delta"])
    assert 0.5 < warm.mean() < 5.0                              # SSP2-4.5, 2050s vs 1995-2014: a few degrees at most
    ratio = np.array(d["median"]["pr_ratio"])
    assert 0.6 < ratio.min() and ratio.max() < 1.8


def test_model_spread_brackets_the_median():
    d = cf.deltas_at(45.42, -75.70, period="2041_2060")
    for var in cf.VARIABLES:
        lo, hi, mid = (np.array(x) for x in (d["spread"][var]["min"], d["spread"][var]["max"], d["median"][var]))
        assert (lo <= mid + 1e-6).all() and (mid <= hi + 1e-6).all()
    assert set(d["models"]) == {"ACCESS-CM2", "MPI-ESM1-2-HR", "MRI-ESM2-0"}   # models kept separate


def test_any_point_in_the_region_works_and_far_points_are_refused():
    for lat, lon in [(42.0, -82.5), (44.0, -77.0), (45.6, -75.0), (43.2, -81.9)]:
        assert cf.deltas_at(lat, lon, period="2041_2060")["median"]["tmax_c_delta"]
    with pytest.raises(cf.OutsideGridError):
        cf.deltas_at(60.0, -100.0, period="2041_2060")


def test_apply_deltas_shifts_weather_without_mutating_it():
    w = load_weather("guelph").loc["2005":"2007"]
    before = w.copy()
    d = cf.deltas_at(43.55, -80.25, period="2041_2060")["median"]
    f = cf.apply_deltas(w, d)
    assert w.equals(before)                                     # original untouched
    assert (f["tmax_c"] - w["tmax_c"]).mean() > 0.5
    assert (f["tmin_c"] <= f["tmax_c"]).all()
    assert f["solar_mj_m2"].equals(w["solar_mj_m2"])            # only temperature and rain change
    assert f["precip_mm"].sum() == pytest.approx(
        (w["precip_mm"] * np.array(d["pr_ratio"])[w.index.month.values - 1]).sum())
