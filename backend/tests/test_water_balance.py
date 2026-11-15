import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from engine import et0, water_balance as wb
from engine.weather import load_reference, load_weather


def test_no_rain_depletes_then_stresses():
    out = wb.run_bucket(etc=[5.0] * 30, rain=[0.0] * 30, taw=100, p=0.5)
    # full store, 5 mm/day, readily available water 50 mm: stress starts when depletion > 50
    assert not out["stressed"][:10].any()
    assert out["stressed"][11:].all()
    assert out["eta"][:10].tolist() == [5.0] * 10
    assert out["eta"][-1] < 5.0
    assert out["store"].min() >= 0


def test_plenty_of_rain_means_no_shortfall():
    out = wb.run_bucket(etc=[5.0] * 30, rain=[6.0] * 30, taw=100, p=0.5)
    assert not out["stressed"].any()
    assert out["eta"].sum() == pytest.approx(150.0)
    assert out["store"].max() <= 100


def test_excess_rain_is_lost_not_stored():
    out = wb.run_bucket(etc=[0.0] * 3, rain=[500.0, 0.0, 0.0], taw=100, p=0.5)
    assert out["store"].tolist() == [100.0, 100.0, 100.0]


def test_eta_never_exceeds_demand_or_store():
    rng = np.random.default_rng(0)
    etc, rain = rng.uniform(0, 7, 200), rng.choice([0, 0, 0, 12.0], 200)
    out = wb.run_bucket(etc, rain, taw=120, p=0.55)
    assert (out["eta"] <= etc + 1e-9).all() and (out["store"] >= 0).all()


@pytest.fixture(scope="module")
def guelph():
    weather = load_weather("guelph")
    frame = weather.copy()
    frame.attrs["latitude"] = 43.55
    return frame, load_reference("crops"), load_reference("soil_texture")


def test_real_corn_season_is_sane(guelph):
    frame, crops, soils = guelph
    m = wb.simulate_years(frame, crops["corn"], soils["loam"], range(1984, 2025))
    assert len(m) >= 25
    assert (m["shortfall_mm"] >= 0).all() and (m["eta_mm"] <= m["etc_mm"] + 1e-6).all()
    s = wb.summarize(m)
    assert s["shortfall_mm_dry"] >= s["shortfall_mm_typical"]
    assert s["unmet_demand_days_typical"] >= 0
    assert "survival_rate" not in s


def test_lighter_soil_is_drier(guelph):
    frame, crops, soils = guelph
    sandy = wb.summarize(wb.simulate_years(frame, crops["corn"], soils["sandy_loam"], range(1990, 2025)))
    loam = wb.summarize(wb.simulate_years(frame, crops["corn"], soils["loam"], range(1990, 2025)))
    assert sandy["shortfall_mm_typical"] >= loam["shortfall_mm_typical"]


def test_crop_without_data_returns_none(guelph):
    frame, crops, soils = guelph
    assert wb.simulate_season(frame, crops["cereal_rye"], soils["loam"], 2010) is None
    assert wb.simulate_years(frame, crops["red_clover"], soils["loam"], range(2000, 2010)).empty


def test_wheat_runs_autumn_to_next_harvest(guelph):
    frame, crops, soils = guelph
    r = wb.simulate_season(frame, crops["winter_wheat"], soils["loam"], 2010)
    assert r["season_start"].startswith("2009-09") and r["season_end"].startswith("2010-07")
