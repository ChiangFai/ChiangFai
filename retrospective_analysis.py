import argparse
import datetime
import ee
import folium

ee.Initialize(project='burning-hammer')

REGION_NAME = "Chiang Mai"
chiang_mai = ee.Geometry.Rectangle([98.2, 18.0, 99.5, 20.0])
YEARS = range(2000, 2026)  # 2000–2025

# Fire season: weeks 6–20 (early Feb → mid May)
SEASON_START_WEEK = 6
SEASON_END_WEEK = 20


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


def get_weekly_fire_presence(year, week):
    """Binary image: 1 where any fire detected in ISO week of year."""
    start = datetime.date.fromisocalendar(year, week, 1)
    end   = datetime.date.fromisocalendar(year, week, 7)
    weekly = (
        ee.ImageCollection("FIRMS")
        .filterDate(str(start), str(end + datetime.timedelta(days=1)))
        .filterBounds(chiang_mai)
        .select("T21")
    )
    img = ee.Image(
        ee.Algorithms.If(
            weekly.size().gt(0),
            weekly.count().gt(0).rename(f"w{week:02d}"),
            ee.Image.constant(0).rename(f"w{week:02d}")
        )
    )
    return img.toFloat()


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


def export_weekly(year):
    """
    Export one band per ISO week of the fire season for a given year.
    Bands: w06, w07, ..., w20  (weeks 6–20 = early Feb to mid May).
    Output TIF: ChiangFai/ChiangMai_fire_weekly_YYYY_FIRMS.tif
    Pass the downloaded TIF to:  python process_retrospective.py --weekly <path>
    """
    bands = [
        get_weekly_fire_presence(year, w)
        for w in range(SEASON_START_WEEK, SEASON_END_WEEK + 1)
    ]
    multiband = ee.Image.cat(bands)

    task = ee.batch.Export.image.toDrive(
        image=multiband,
        description=f"ChiangMai_fire_weekly_{year}_FIRMS",
        scale=375,        # VIIRS 375 m — finer than annual 1 km
        region=chiang_mai,
        maxPixels=1e9,
        folder="ChiangFai",
        fileFormat="GeoTIFF",
    )
    task.start()
    week_labels = [f"w{w:02d}" for w in range(SEASON_START_WEEK, SEASON_END_WEEK + 1)]
    print(f"Weekly export started for {year}")
    print(f"Bands: {', '.join(week_labels)}")
    print(f"Scale: 375 m  |  Expected: 15–25 minutes")
    print("Download from Google Drive → ChiangFai/ when done, then run:")
    print(f"  python process_retrospective.py --weekly ChiangMai_fire_weekly_{year}_FIRMS.tif")


def build_local_map():
    m = folium.Map(location=[18.8, 98.9], zoom_start=9)
    m.save("reports/chiang_mai_burn_map.html")
    print("Saved: reports/chiang_mai_burn_map.html")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="GEE fire export for ChiangFai")
    parser.add_argument("--weekly", type=int, metavar="YEAR",
                        help="Export weekly fire season data for YEAR instead of the full annual stack")
    args = parser.parse_args()

    if args.weekly:
        export_weekly(args.weekly)
    else:
        export_multiband()
        build_local_map()
