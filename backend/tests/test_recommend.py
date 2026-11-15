import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from engine import ratings, recommend as R, rotations
from engine.weather import load_reference

CROPS, RULES = load_reference("crops"), load_reference("rotation_rules")
REQ = {"lat": 43.55, "lon": -80.25, "soil": "loam", "current_rotation": ["corn", "soybean"]}


def rot(*years):
    return tuple(y if isinstance(y, tuple) else (y, None) for y in years)


def test_nitrogen_legume_credit_lowers_demand():
    corn_soy = ratings.nitrogen_rating(rot("corn", "soybean"), CROPS)
    corn_corn = ratings.nitrogen_rating(rot("corn", "corn"), CROPS)
    assert corn_soy["index"] < corn_corn["index"] == 3.0      # corn after soybean drops a level
    assert corn_soy["legume_credit_crops"] == ["corn"]


def test_clover_cover_gives_credit_to_next_crop():
    with_clover = ratings.nitrogen_rating(rot(("winter_wheat", "red_clover"), "corn"), CROPS)
    without = ratings.nitrogen_rating(rot("winter_wheat", "corn"), CROPS)
    assert with_clover["index"] < without["index"]


def test_cover_rating_rises_with_cover_crops():
    bare = ratings.cover_rating(rot("corn", "soybean"), CROPS)
    covered = ratings.cover_rating(rot(("corn", "cereal_rye"), ("soybean", "cereal_rye")), CROPS)
    assert bare["label"] == "low" and covered["fraction"] > bare["fraction"]


def test_pest_break_flags_repeats():
    assert ratings.pest_break_rating(rot("corn", "corn"), CROPS, RULES)["label"] != "good"
    assert ratings.pest_break_rating(rot("corn", "soybean", "winter_wheat"), CROPS, RULES)["label"] == "good"


def test_generator_respects_disallowed_successions():
    for seq in rotations.main_sequences(RULES):
        assert not any(seq[i - 1] == "winter_wheat" == seq[i] for i in range(len(seq)))
    assert len(set(rotations.main_sequences(RULES))) == len(rotations.main_sequences(RULES))


def test_constraints_must_avoid_equipment():
    cands = rotations.all_candidates(RULES)
    assert all("corn" in rotations.crops_in(r) for r in rotations.filter_candidates(cands, CROPS, must_include=["corn"]))
    assert all("cereal_rye" not in rotations.crops_in(r) for r in rotations.filter_candidates(cands, CROPS, avoid=["cereal_rye"]))
    no_drill = rotations.filter_candidates(cands, CROPS, equipment=["planter", "combine"])
    assert no_drill and all("winter_wheat" not in rotations.crops_in(r) for r in no_drill)


def test_recommend_returns_distinct_constrained_options():
    out = R.recommend({**REQ, "must_include": ["corn"]})
    assert 3 <= len(out["options"]) <= 5
    keys = {tuple(y["crop"] for y in o["rotation"]) for o in out["options"]}
    assert len(keys) == len(out["options"])                       # distinct main-crop sequences
    for o in out["options"]:
        assert any(y["crop"] == "corn" for y in o["rotation"])    # must-grow honoured
        assert o["why"] and o["confidence"] and "vs_baseline" in o
        assert o["vs_baseline"]["water_use_pct"] % 5 == 0         # rounded to nearest 5%
    assert out["baseline"]["name"] == "corn → soybean"


def test_avoided_crop_never_appears():
    out = R.recommend({**REQ, "avoid": ["winter_wheat"]})
    assert out["options"]
    for o in out["options"]:
        assert all(y["crop"] != "winter_wheat" for y in o["rotation"])


def test_impossible_constraints_say_so():
    # without wheat or rye, the only corn/soybean rotation left is the farmer's own
    with pytest.raises(R.InputError, match="constraints"):
        R.recommend({**REQ, "avoid": ["winter_wheat", "cereal_rye"]})


def test_default_baseline_is_labelled():
    out = R.recommend({"lat": 43.55, "lon": -80.25, "soil": "clay"})
    assert out["inputs_used"]["default_baseline"] and any("default" in w for w in out["warnings"])


def test_bad_inputs_raise_clear_errors():
    with pytest.raises(R.InputError):
        R.recommend({**REQ, "soil": "gravel"})
    with pytest.raises(R.InputError):
        R.recommend({**REQ, "lat": 51.0, "lon": -90.0})            # far outside Southern Ontario
    with pytest.raises(R.InputError):
        R.recommend({**REQ, "must_include": ["corn"], "avoid": ["corn"]})


def test_unknown_must_grow_crop_is_flagged_not_modelled():
    out = R.recommend({**REQ, "must_include": ["rice"]})
    assert any("rice" in w for w in out["warnings"])


def test_api_endpoints():
    testclient = pytest.importorskip("fastapi.testclient")
    from api.main import app
    c = testclient.TestClient(app)
    assert c.get("/health").json() == {"status": "ok"}
    assert len(c.get("/anchors").json()) == 12
    assert c.get("/snap", params={"lat": 43.6, "lon": -79.4}).json()["id"] == "toronto"
    assert c.get("/snap", params={"lat": 60, "lon": -100}).status_code == 422
    assert {"soils", "main_crops", "cover_crops"} <= set(c.get("/reference").json())
    r = c.post("/recommend", json={"lat": 43.55, "lon": -80.25, "current_rotation": ["corn", "soybean"]})
    assert r.status_code == 200 and len(r.json()["options"]) >= 3
    assert c.post("/recommend", json={"lat": 43.55, "lon": -80.25, "soil": "gravel"}).status_code == 422
    assert c.get("/evidence").json()["limitations"]
