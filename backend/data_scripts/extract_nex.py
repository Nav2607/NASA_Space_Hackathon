import argparse
import concurrent.futures
import csv
import datetime as dt
import io
import json
import math
import pathlib
import time
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET

BASE = "https://ds.nccs.nasa.gov/thredds/"
NS = {
    "t": "http://www.unidata.ucar.edu/namespaces/thredds/InvCatalog/v1.0"
}
MODELS = ["ACCESS-CM2", "MPI-ESM1-2-HR", "MRI-ESM2-0"]


def download(url):
    for attempt in range(3):
        try:
            with urllib.request.urlopen(url, timeout=55) as response:
                return response.read().decode()
        except Exception:
            if attempt == 2:
                raise
            time.sleep(attempt + 1)


def extract_variable(model, variable, year, args):
    folder = (
        f"AMES/NEX/GDDP-CMIP6/{model}/{args.scenario}/"
        f"r1i1p1f1/{variable}/"
    )
    catalog = ET.fromstring(
        download(BASE + "catalog/" + folder + "catalog.xml")
    )

    filename = (
        f"{variable}_day_{model}_{args.scenario}_"
        f"r1i1p1f1_gn_{year}_v2.0.nc"
    )
    paths = [
        entry.attrib["urlPath"]
        for entry in catalog.findall(".//t:dataset", NS)
        if entry.attrib.get("name") == filename
    ]
    if len(paths) != 1:
        raise ValueError(f"Dataset not found: {filename}")

    query = urllib.parse.urlencode({
        "var": variable,
        "latitude": args.lat,
        "longitude": args.lon,
        "time_start": f"{year}-01-01T00:00:00Z",
        "time_end": f"{year}-12-31T23:59:59Z",
        "accept": "csv",
    })
    url = BASE + "ncss/grid/" + paths[0] + "?" + query

    cache = (
        pathlib.Path(".nex-cache")
        / f"{args.lat}_{args.lon}"
        / model
        / args.scenario
        / f"{variable}_{year}.csv"
    )
    if cache.exists():
        raw = cache.read_text(encoding="utf-8")
    else:
        raw = download(url)
        cache.parent.mkdir(parents=True, exist_ok=True)
        cache.write_text(raw, encoding="utf-8")

    reader = csv.DictReader(io.StringIO(raw))
    fields = reader.fieldnames or []
    value_key = next(
        key for key in fields if key.startswith(variable + "[")
    )
    latitude_key = next(
        key for key in fields if key.startswith("latitude[")
    )
    longitude_key = next(
        key for key in fields if key.startswith("longitude[")
    )

    expected_unit = "kg m-2 s-1" if variable == "pr" else "K"
    if f'unit="{expected_unit}"' not in value_key:
        raise ValueError(f"Unexpected source units: {value_key}")

    values = {}
    grid = None

    for row in reader:
        date = dt.date.fromisoformat(row["time"][:10])
        value = float(row[value_key])
        cell = (
            float(row[latitude_key]),
            float(row[longitude_key]),
        )

        if grid is not None and grid != cell:
            raise ValueError("Grid cell changed within a file")
        grid = cell

        if (
            date.year != year
            or date.isoformat() in values
            or not math.isfinite(value)
        ):
            raise ValueError("Invalid date or missing value")

        if variable == "pr":
            if not 0 <= value < 1:
                raise ValueError("Invalid precipitation flux")
            value *= 86400
        else:
            if not 150 < value < 350:
                raise ValueError("Invalid temperature")
            value -= 273.15

        values[date.isoformat()] = round(value, 5)

    first_day = dt.date(year, 1, 1)
    day_count = (dt.date(year + 1, 1, 1) - first_day).days
    expected_dates = {
        (first_day + dt.timedelta(days=i)).isoformat()
        for i in range(day_count)
    }
    if set(values) != expected_dates:
        raise ValueError(
            "Incomplete year: check missing dates or source calendar"
        )

    return model, variable, year, values, grid, url


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--lat", type=float, default=43.0)
    parser.add_argument("--lon", type=float, default=-81.25)
    parser.add_argument("--start", type=int, default=2041)
    parser.add_argument("--end", type=int, default=2060)
    parser.add_argument(
        "--scenario",
        choices=["ssp245", "ssp585"],
        default="ssp245",
    )
    parser.add_argument(
        "--output",
        default="backend/data/nex/london_demo.json",
    )
    args = parser.parse_args()

    if not (
        -90 <= args.lat <= 90
        and -180 <= args.lon <= 180
        and 2015 <= args.start <= args.end <= 2100
    ):
        parser.error("Invalid coordinates or year range")

    data = {model: {} for model in MODELS}
    grids = {}
    sources = []
    names = {
        "tasmin": "tmin_c",
        "tasmax": "tmax_c",
        "pr": "precipitation_mm",
    }

    jobs = [
        (model, variable, year, args)
        for model in MODELS
        for variable in names
        for year in range(args.start, args.end + 1)
    ]

    with concurrent.futures.ThreadPoolExecutor(max_workers=6) as pool:
        futures = [
            pool.submit(extract_variable, *job)
            for job in jobs
        ]
        for number, future in enumerate(
            concurrent.futures.as_completed(futures), 1
        ):
            model, variable, year, values, grid, url = future.result()

            if model in grids and grids[model] != grid:
                raise ValueError("Variables use different grid cells")
            grids[model] = grid

            for date, value in values.items():
                daily = data[model].setdefault(date, {"date": date})
                daily[names[variable]] = value

            sources.append({
                "model": model,
                "variable": variable,
                "year": year,
                "url": url,
            })
            print(
                f"{number}/{len(jobs)}: {model} {variable} {year}",
                flush=True,
            )

    for model in MODELS:
        for row in data[model].values():
            if len(row) != 4 or row["tmin_c"] > row["tmax_c"]:
                raise ValueError("Incomplete or inconsistent daily data")

    result = {
        "dataset": "NEX-GDDP-CMIP6",
        "version": "2.0",
        "source_type": "Projected",
        "scenario": args.scenario,
        "member": "r1i1p1f1",
        "period": {"start": args.start, "end": args.end},
        "requested_location": {
            "latitude": args.lat,
            "longitude": args.lon,
        },
        "location_note": "Demo extraction; confirm your app's anchor location",
        "extracted_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
        "units": {
            "tmin_c": "degC",
            "tmax_c": "degC",
            "precipitation_mm": "mm/day",
        },
        "models": [
            {
                "name": model,
                "grid_location": {
                    "latitude": grids[model][0],
                    "longitude": grids[model][1],
                },
                "daily": [
                    data[model][date]
                    for date in sorted(data[model])
                ],
            }
            for model in MODELS
        ],
        "sources": sorted(
            sources,
            key=lambda item: (
                item["model"], item["year"], item["variable"]
            ),
        ),
    }

    output = pathlib.Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_suffix(".tmp")
    temporary.write_text(
        json.dumps(result, indent=2, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    temporary.replace(output)
    print(f"Saved: {output}")


if __name__ == "__main__":
    main()