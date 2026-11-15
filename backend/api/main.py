"""Field Shift Canada API.  Run from the repo root:

    python -m uvicorn backend.api.main:app --reload --port 8000

Docs for the frontend: http://localhost:8000/docs
"""
import json
import sys
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from engine import recommend as R                       # noqa: E402
from engine.weather import DATA_DIR, load_reference     # noqa: E402

app = FastAPI(title="Field Shift Canada API", version="0.1.0",
              description="Educational decision support for comparing crop rotations in Southern Ontario. Not agronomic advice.")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])


class Priorities(BaseModel):
    water: float = Field(0.25, ge=0, le=1)
    nitrogen: float = Field(0.25, ge=0, le=1)
    soil_cover: float = Field(0.25, ge=0, le=1)
    weather_risk: float = Field(0.25, ge=0, le=1)


class RecommendRequest(BaseModel):
    lat: float = Field(..., ge=41, le=47)
    lon: float = Field(..., ge=-84, le=-74)
    soil: str = "loam"                                  # sandy_loam | loam | clay_loam | clay
    tile_drainage: bool = False
    irrigation: bool = False
    equipment: Optional[list[str]] = None               # planter, grain_drill, combine; null = assume all
    current_rotation: list[str] = Field(default_factory=list, max_length=4)
    must_include: list[str] = Field(default_factory=list)
    avoid: list[str] = Field(default_factory=list)
    priorities: Priorities = Priorities()


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/anchors")
def anchors():
    """The 12 data points with map-ready summary statistics."""
    return json.loads((DATA_DIR / "processed" / "anchor_summary.json").read_text(encoding="utf-8"))


@app.get("/snap")
def snap(lat: float, lon: float):
    """Which data point a clicked location uses."""
    try:
        return R.snap(lat, lon)
    except R.InputError as err:
        raise HTTPException(status_code=422, detail=str(err))


@app.get("/reference")
def reference():
    """Options for the farm form, built from the same cited tables the engine uses."""
    crops, soils, _ = load_reference("crops"), load_reference("soil_texture"), None
    return {
        "soils": [{"id": k, "label": v["label"]} for k, v in soils.items() if not k.startswith("_")],
        "main_crops": [{"id": k, "label": R.CROP_NAMES[k], "needs_equipment": crops[k]["needs_equipment"],
                        "data_quality": crops[k]["data_quality"]} for k in ("corn", "soybean", "winter_wheat")],
        "cover_crops": [{"id": k, "label": R.CROP_NAMES[k], "needs_equipment": crops[k]["needs_equipment"],
                         "data_quality": crops[k]["data_quality"]} for k in ("cereal_rye", "red_clover")],
        "equipment": ["planter", "grain_drill", "combine"],
        "priorities": list(R.DEFAULT_PRIORITIES),
    }


@app.post("/recommend")
def recommend(req: RecommendRequest):
    body = req.model_dump()
    try:
        return R.recommend(body)
    except R.InputError as err:
        raise HTTPException(status_code=422, detail=str(err))


@app.get("/evidence")
def evidence():
    sources = load_reference("sources")
    return {
        "data_sources": [
            {"name": "NASA POWER", "used_for": "Daily temperature, rain, humidity, wind and sunlight, 1981-2024",
             "resolution": "about 0.5 degrees (roughly 50 km grid cells)", "tag": "NASA-derived (satellite and model based, not measured on your field)"},
            {"name": "FAO-56 (Allen et al. 1998)", "used_for": "Evaporation method, crop coefficients, stage lengths, rooting depth", "tag": "Modeled"},
            {"name": "AquaCrop default soil and crop parameters", "used_for": "Soil water holding capacity by texture, crop heat limits", "tag": "Modeled (typical values)"},
            {"name": "Rotation rules", "used_for": "Nitrogen, soil cover, pest-break and timing ratings", "tag": "Rule-based / Assumed"},
        ],
        "limitations": [
            "Weather data is regional (about 50 km), not field-level.",
            "Water results are simplified relative comparisons between rotations, not field predictions. They ignore tile drainage, water tables and runoff.",
            "Cover-crop water use is not modelled; water figures cover the main crops only.",
            "Nitrogen, soil-cover and pest-break ratings are qualitative and rule-based; actual fertilizer needs depend on soil tests and local guidance.",
            "There is no yield data, so lower water use does not mean a better rotation.",
            "Some thresholds and crop calendars are assumptions (shown as 'Assumed'). Percentages are rounded to the nearest 5%.",
            "Educational decision support, not agronomic advice. Talk to a local agronomist.",
        ],
        "citations": {k: {"citation": v["citation"], "url": v["url"]} for k, v in sources.items()},
    }
