"""Extract AAFC 2025 crop classifications for Southern Ontario."""
"""Extract AAFC 2025 crop classifications for Southern Ontario."""
import csv
import datetime as dt
import io
import json
import math
from collections import Counter
from pathlib import Path
import shutil
import urllib.request
import zipfile

import numpy as np
import rasterio
from rasterio.windows import Window, from_bounds
from rasterio.warp import transform_bounds

ARCHIVE_URL = (
    "https://agriculture.canada.ca/atlas/data_donnees/"
    "annualCropInventory/data_donnees/tif/2025/aci_2025_on_v1.zip"
)
LEGEND_URL = (
    "https://agriculture.canada.ca/atlas/data_donnees/"
    "annualCropInventory/supportdocument_documentdesupport/"
    "aci_crop_classifications_iac_classifications_des_cultures.csv"
)

# West, south, east, north: matches the project's NEX processing area.
BBOX = [-83.6, 41.6, -74.4, 45.8]
CACHE = Path(".aafc-cache")
OUTPUT = Path("backend/data/aafc/2025")
MEMBER = "aci_2025_on_v1.tif"


def download(url, destination):
    if destination.exists():
        print(f"Using cached file: {destination}", flush=True)
        return

    temporary = destination.with_suffix(destination.suffix + ".part")
    with urllib.request.urlopen(url, timeout=120) as response:
        expected = int(response.headers.get("Content-Length", 0))
        total = 0
        with temporary.open("wb") as output:
            while chunk := response.read(8 * 1024 * 1024):
                output.write(chunk)
                total += len(chunk)
                print(f"Downloaded {total / 1e6:.0f} MB", flush=True)

        if expected and total != expected:
            raise ValueError("Incomplete download. Run the script again.")

    temporary.replace(destination)


def main():
    print("Starting AAFC 2025 extraction...", flush=True)
    CACHE.mkdir(parents=True, exist_ok=True)
    OUTPUT.mkdir(parents=True, exist_ok=True)

    archive = CACHE / "aci_2025_on_v1.zip"
    source = CACHE / MEMBER
    download(ARCHIVE_URL, archive)

    if not source.exists():
        print("Unpacking the crop classification raster...", flush=True)
        with zipfile.ZipFile(archive) as bundle:
            # Use crop classifications, not the separate confidence TIFF.
            with bundle.open(MEMBER) as incoming:
                with source.with_suffix(".part").open("wb") as outgoing:
                    shutil.copyfileobj(incoming, outgoing)
        source.with_suffix(".part").replace(source)

    legend_file = CACHE / "official_legend.csv"
    download(LEGEND_URL, legend_file)
    raw = legend_file.read_bytes()

    try:
        legend_text = raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        legend_text = raw.decode("cp1252")

    legend = {
        int(row["Code"]): row
        for row in csv.DictReader(io.StringIO(legend_text))
    }

    target = OUTPUT / "southern_ontario_2025.tif"
    temporary = OUTPUT / "southern_ontario_2025.partial.tif"
    counts = Counter()

    with rasterio.open(source) as src:
        if src.count != 1 or src.dtypes[0] != "uint8":
            raise ValueError("Unexpected classification raster format.")

        bounds = transform_bounds(
            "EPSG:4326", src.crs, *BBOX, densify_pts=21
        )
        requested = from_bounds(*bounds, transform=src.transform)

        left = math.floor(requested.col_off)
        top = math.floor(requested.row_off)
        right = math.ceil(requested.col_off + requested.width)
        bottom = math.ceil(requested.row_off + requested.height)

        window = Window(
            left, top, right - left, bottom - top
        ).intersection(Window(0, 0, src.width, src.height))

        profile = src.profile.copy()
        profile.update(
            width=int(window.width),
            height=int(window.height),
            transform=src.window_transform(window),
            compress="deflate",
            tiled=True,
            blockxsize=512,
            blockysize=512,
        )

        with rasterio.open(temporary, "w", **profile) as dst:
            dst.write_colormap(1, src.colormap(1))

            for number, (_, block) in enumerate(dst.block_windows(1), 1):
                source_block = Window(
                    window.col_off + block.col_off,
                    window.row_off + block.row_off,
                    block.width,
                    block.height,
                )
                values = src.read(1, window=source_block)
                dst.write(values, 1, window=block)

                codes, frequencies = np.unique(
                    values, return_counts=True
                )
                counts.update(
                    dict(zip(map(int, codes), map(int, frequencies)))
                )

                if number % 100 == 0:
                    print(
                        f"Extracted {number} raster blocks",
                        flush=True,
                    )

        unknown = set(counts) - set(legend) - {0}
        if unknown:
            raise ValueError(f"Unexpected crop codes: {sorted(unknown)}")

        metadata = {
            "dataset": "AAFC Annual Crop Inventory",
            "year": 2025,
            "source_type": "Satellite-derived crop classification",
            "archive_url": ARCHIVE_URL,
            "source_member": MEMBER,
            "legend_url": LEGEND_URL,
            "licence_url": (
                "https://open.canada.ca/en/"
                "open-government-licence-canada"
            ),
            "extracted_at_utc": dt.datetime.now(
                dt.timezone.utc
            ).isoformat(),
            "requested_bbox_wgs84": BBOX,
            "crs_wkt": src.crs.to_wkt(),
            "pixel_size_m": list(src.res),
            "source_nodata": src.nodata,
            "note": (
                "Native-grid bounding-window extraction, not an official "
                "Southern Ontario administrative boundary. No resampling. "
                "Code 0 is unlisted/unknown and preserved. Classifications "
                "are not verified field boundaries."
            ),
            "class_pixel_counts": {
                str(code): {
                    "label": (
                        legend[code]["Label"]
                        if code in legend else "Unlisted/unknown"
                    ),
                    "pixels": count,
                }
                for code, count in sorted(counts.items())
            },
        }

    with rasterio.open(temporary) as check:
        metadata["width"] = check.width
        metadata["height"] = check.height
        metadata["output_bounds_native_crs"] = list(check.bounds)

    temporary.replace(target)
    (OUTPUT / "legend.csv").write_text(legend_text, encoding="utf-8")
    (OUTPUT / "metadata.json").write_text(
        json.dumps(metadata, indent=2), encoding="utf-8"
    )

    print(f"Saved: {target}")
    print("Saved: legend.csv and metadata.json")


if __name__ == "__main__":
    main()