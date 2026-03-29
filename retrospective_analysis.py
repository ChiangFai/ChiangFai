import ee
import geopandas as gpd
import pandas as pd
from datetime import datetime
import folium

ee.Initialize(project='burning-hammer')

# === CONFIG ===
REGION_NAME = "Chiang Mai"

# Tightened to actual Chiang Mai province — excludes Myanmar to the west
chiang_mai = ee.Geometry.Rectangle([98.2, 18.0, 99.5, 20.0])

YEARS = range(2000, 2026)  # 2000–2025 inclusive — FIRMS MODIS goes back to 2000


# === 1. Annual fire recurrence using FIRMS active fire detections ===
# FIRMS in GEE = MODIS Terra 1km active fires, daily, back to 2000.
# This catches small agricultural burns that dNBR misses, and has no
# cloud/smoke ambiguity — if a satellite saw fire, it's recorded.

def get_annual_fire_presence(year):
    """
    Returns a binary image: 1 where at least one fire was detected
    during the fire season (Jan–May) of the given year, 0 elsewhere.
    Uses FIRMS MODIS 1km active fire detections.
    """
    season = (
        ee.ImageCollection("FIRMS")
        .filterDate(f"{year}-01-01", f"{year}-05-31")
        .filterBounds(chiang_mai)
        .select("T21")  # brightness temperature band; presence = fire detected
    )

    # count() = number of days with detection per pixel; gt(0) = any fire this season
    annual = ee.Image(
        ee.Algorithms.If(
            season.size().gt(0),
            season.count().gt(0).rename("fire_presence"),
            ee.Image.constant(0).rename("fire_presence")
        )
    )
    return annual.toFloat().set("year", year)


# === 2. Build recurrence raster: how many years did each pixel burn? ===
fire_collection = ee.ImageCollection([get_annual_fire_presence(y) for y in YEARS])
recurrence = fire_collection.sum().toFloat().rename("burn_count")


# === 3. Export to Google Drive ===
def export_recurrence():
    task = ee.batch.Export.image.toDrive(
        image=recurrence,
        description=f"{REGION_NAME}_burn_recurrence_2000_2025_FIRMS",
        scale=1000,          # FIRMS native resolution is 1km
        region=chiang_mai,
        maxPixels=1e9,
        folder="ChiangFai",
        fileFormat="GeoTIFF",
    )
    task.start()
    print("Export started — check Tasks tab at code.earthengine.google.com")
    print("Expected: 5–15 minutes at 1km resolution")


# === 4. Quick local map ===
def build_local_map():
    m = folium.Map(location=[18.8, 98.9], zoom_start=9)
    m.save("reports/chiang_mai_burn_map.html")
    print("Saved: reports/chiang_mai_burn_map.html")
    return m


if __name__ == "__main__":
    export_recurrence()
    build_local_map()
