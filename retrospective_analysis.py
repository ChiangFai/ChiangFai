import ee
import folium

ee.Initialize(project='burning-hammer')

REGION_NAME = "Chiang Mai"
chiang_mai = ee.Geometry.Rectangle([98.2, 18.0, 99.5, 20.0])
YEARS = range(2000, 2026)  # 2000–2025


def get_annual_fire_presence(year):
    """Binary image: 1 where any fire detected Jan–May of year."""
    season = (
        ee.ImageCollection("FIRMS")
        .filterDate(f"{year}-01-01", f"{year}-05-31")
        .filterBounds(chiang_mai)
        .select("T21")
    )
    annual = ee.Image(
        ee.Algorithms.If(
            season.size().gt(0),
            season.count().gt(0).rename(f"y{year}"),
            ee.Image.constant(0).rename(f"y{year}")
        )
    )
    return annual.toFloat()


def export_multiband():
    """
    Export one band per year (y2000…y2025).
    Allows the app to filter any arbitrary date range without re-running GEE.
    """
    bands = [get_annual_fire_presence(y) for y in YEARS]
    multiband = ee.Image.cat(bands)

    task = ee.batch.Export.image.toDrive(
        image=multiband,
        description=f"{REGION_NAME}_fire_by_year_2000_2025_FIRMS",
        scale=1000,
        region=chiang_mai,
        maxPixels=1e9,
        folder="ChiangFai",
        fileFormat="GeoTIFF",
    )
    task.start()
    print("Export started — check Tasks tab at code.earthengine.google.com")
    print("One band per year: y2000, y2001, ..., y2025")
    print("Expected: 10–20 minutes")


def build_local_map():
    m = folium.Map(location=[18.8, 98.9], zoom_start=9)
    m.save("reports/chiang_mai_burn_map.html")
    print("Saved: reports/chiang_mai_burn_map.html")


if __name__ == "__main__":
    export_multiband()
    build_local_map()
