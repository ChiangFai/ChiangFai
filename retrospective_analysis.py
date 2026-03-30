"""
GEE fire export for ChiangFai.

Annual stack (default):
  python retrospective_analysis.py
  → exports fire_by_year_2000_2025_FIRMS.tif  (one band per year)

Weekly — ALL years in one shot:
  python retrospective_analysis.py --weekly-all
  → exports fire_weekly_all_years_FIRMS.tif
    390 bands: y2000w06, y2000w07, ..., y2025w20
    One TIF, one download, covers 2000-2025 at 1km weekly resolution.

Weekly — single year (for re-runs or additions):
  python retrospective_analysis.py --weekly 2024
"""

import argparse
import datetime
import ee
import folium

ee.Initialize(project='burning-hammer')

REGION_NAME = "Chiang Mai"
chiang_mai = ee.Geometry.Rectangle([98.2, 18.0, 99.5, 20.0])
YEARS = list(range(2000, 2026))   # 2000–2025
SEASON_START_WEEK = 6             # early Feb
SEASON_END_WEEK = 20              # mid May


# ── Helpers ───────────────────────────────────────────────────────────────────

def annual_presence(year):
    """Binary image: 1 where any FIRMS fire Jan–May of year."""
    return (
        ee.ImageCollection("FIRMS")
        .filterDate(f"{year}-01-01", f"{year}-05-31")
        .filterBounds(chiang_mai)
        .select("T21")
        .count()
        .gt(0)
        .unmask(0)
        .rename(f"y{year}")
        .toFloat()
    )


def weekly_presence(year, week):
    """Binary image: 1 where any FIRMS fire in ISO week of year."""
    start = datetime.date.fromisocalendar(year, week, 1)
    end   = datetime.date.fromisocalendar(year, week, 7) + datetime.timedelta(days=1)
    return (
        ee.ImageCollection("FIRMS")
        .filterDate(str(start), str(end))
        .filterBounds(chiang_mai)
        .select("T21")
        .count()
        .gt(0)
        .unmask(0)
        .rename(f"y{year}w{week:02d}")
        .toFloat()
    )


# ── Exports ───────────────────────────────────────────────────────────────────

def export_annual():
    """One band per year: y2000 … y2025."""
    bands = [annual_presence(y) for y in YEARS]
    task = ee.batch.Export.image.toDrive(
        image=ee.Image.cat(bands),
        description="ChiangMai_fire_by_year_2000_2025_FIRMS",
        scale=1000,
        region=chiang_mai,
        maxPixels=1e9,
        folder="ChiangFai",
        fileFormat="GeoTIFF",
    )
    task.start()
    print("Annual export started.")
    print("Bands: y2000 … y2025  |  Scale: 1km  |  ~10–20 min")
    print("Then run:  python process_retrospective.py --tif <downloaded.tif>")


def export_weekly_all():
    """
    All 26 years × 15 weeks = 390 bands in a single TIF.
    Band names: y2000w06, y2000w07, … y2025w20
    One export, one download, covers the full 2000-2025 weekly record.
    """
    bands = []
    labels = []
    for year in YEARS:
        for week in range(SEASON_START_WEEK, SEASON_END_WEEK + 1):
            bands.append(weekly_presence(year, week))
            labels.append(f"y{year}w{week:02d}")

    task = ee.batch.Export.image.toDrive(
        image=ee.Image.cat(bands),
        description="ChiangMai_fire_weekly_all_years_FIRMS",
        scale=1000,          # 1km — consistent with annual; keeps file manageable
        region=chiang_mai,
        maxPixels=1e9,
        folder="ChiangFai",
        fileFormat="GeoTIFF",
    )
    task.start()
    print("Weekly (all years) export started.")
    print(f"Bands: {labels[0]} … {labels[-1]}  ({len(labels)} total)")
    print("Scale: 1km  |  ~25–40 min")
    print("Then run:  python process_retrospective.py --weekly-all --tif <downloaded.tif>")


def export_weekly_single(year):
    """One year's fire season weekly bands (re-run or addition)."""
    bands = [weekly_presence(year, w) for w in range(SEASON_START_WEEK, SEASON_END_WEEK + 1)]
    task = ee.batch.Export.image.toDrive(
        image=ee.Image.cat(bands),
        description=f"ChiangMai_fire_weekly_{year}_FIRMS",
        scale=1000,
        region=chiang_mai,
        maxPixels=1e9,
        folder="ChiangFai",
        fileFormat="GeoTIFF",
    )
    task.start()
    print(f"Weekly export started for {year}.")
    print(f"Bands: y{year}w{SEASON_START_WEEK:02d} … y{year}w{SEASON_END_WEEK:02d}")
    print(f"Then run:  python process_retrospective.py --weekly-single --tif <downloaded.tif>")


def build_local_map():
    m = folium.Map(location=[18.8, 98.9], zoom_start=9)
    m.save("reports/chiang_mai_burn_map.html")
    print("Saved: reports/chiang_mai_burn_map.html")


# ── Entry point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="GEE fire export — ChiangFai")
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--weekly-all", action="store_true",
                       help="Export all 26 years of weekly fire season data in one TIF (recommended)")
    group.add_argument("--weekly", type=int, metavar="YEAR",
                       help="Export weekly data for a single year only")
    args = parser.parse_args()

    if args.weekly_all:
        export_weekly_all()
    elif args.weekly:
        export_weekly_single(args.weekly)
    else:
        export_annual()
        build_local_map()
