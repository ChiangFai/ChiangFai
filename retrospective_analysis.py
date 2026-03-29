import ee
import geopandas as gpd
import pandas as pd
from datetime import datetime
import folium
from folium import plugins

ee.Initialize()

# === CONFIG ===
REGION_NAME = "Chiang Mai"
# Rough Chiang Mai province bounding box (lon_min, lat_min, lon_max, lat_max)
chiang_mai = ee.Geometry.Rectangle([97.5, 17.5, 99.5, 20.5])

# To use precise Thai admin boundaries uploaded to GEE:
# tha_tambon = ee.FeatureCollection('projects/yourproject/assets/tha_tambon')

YEARS = range(2018, 2027)


# === 1. Burned Area Mapping using Sentinel-2 dNBR ===
def get_burned_area(year):
    """
    Compute dNBR between pre-fire (Nov) and post-fire (Mar-Apr) composites.
    dNBR > 0.2 is used as burned area threshold (tune for agricultural fires: 0.1–0.3).
    """
    pre = (
        ee.ImageCollection("COPERNICUS/S2_SR_HARMONIZED")
        .filterDate(f"{year}-11-01", f"{year}-12-31")
        .filterBounds(chiang_mai)
        .filter(ee.Filter.lt("CLOUDY_PIXEL_PERCENTAGE", 30))
        .median()
    )

    post = (
        ee.ImageCollection("COPERNICUS/S2_SR_HARMONIZED")
        .filterDate(f"{year + 1}-03-01", f"{year + 1}-04-30")
        .filterBounds(chiang_mai)
        .filter(ee.Filter.lt("CLOUDY_PIXEL_PERCENTAGE", 30))
        .median()
    )

    # NBR = (NIR - SWIR) / (NIR + SWIR)
    nbr_pre = pre.normalizedDifference(["B8", "B12"]).rename("NBR_pre")
    nbr_post = post.normalizedDifference(["B8", "B12"]).rename("NBR_post")

    dnbr = nbr_pre.subtract(nbr_post).rename("dNBR")
    burned = dnbr.gt(0.2).selfMask()
    return burned.set("year", year)


# === 2. Build burn recurrence raster (2018–2026) ===
burn_collection = ee.ImageCollection([get_burned_area(y) for y in YEARS])
recurrence = burn_collection.sum().rename("burn_count")

recurrence_vis = {
    "min": 0,
    "max": len(list(YEARS)),
    "palette": ["yellow", "orange", "red", "darkred"],
}


# === 3. FIRMS active fires (for coordination analysis) ===
firms = (
    ee.ImageCollection("FIRMS")
    .filterBounds(chiang_mai)
    .filterDate("2018-01-01", "2026-12-31")
)


# === 4. Export recurrence map to Google Drive ===
def export_recurrence():
    task = ee.batch.Export.image.toDrive(
        image=recurrence,
        description=f"{REGION_NAME}_burn_recurrence_2018_2026",
        scale=10,
        region=chiang_mai,
        maxPixels=1e10,
    )
    task.start()
    print("Export started — check Google Drive in a few hours")


# === 5. Quick local Folium map skeleton ===
def build_local_map():
    map_center = [18.8, 98.9]  # Chiang Mai city center
    m = folium.Map(location=map_center, zoom_start=9)
    # Add GEE tile layers via getMapId() after ee.Initialize() if running in notebook
    m.save("reports/chiang_mai_burn_map.html")
    print("Saved: reports/chiang_mai_burn_map.html")
    return m


if __name__ == "__main__":
    export_recurrence()
    build_local_map()
