"""
Processes GEE fire GeoTIFFs into CSVs for the Streamlit app.

Annual (default):
  python process_retrospective.py path/to/Chiang_Mai_fire_by_year_2000_2025_FIRMS.tif
  → data/fire_by_year.csv   (latitude, longitude, y2000…y2025)
  → reports/recurrence_map.png

Weekly (fire season drill-down):
  python process_retrospective.py --weekly path/to/ChiangMai_fire_weekly_2024_FIRMS.tif
  → data/fire_by_week.csv   (latitude, longitude, year, week)
    appends/merges with existing rows so multiple years accumulate in one file
"""

import argparse
import os
import re
import sys

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.colors as mcolors

try:
    import rasterio
except ImportError:
    print("Run: pip install rasterio")
    sys.exit(1)

OUTPUT_DIR_DATA = "data"
OUTPUT_DIR_REPORTS = "reports"
os.makedirs(OUTPUT_DIR_DATA, exist_ok=True)
os.makedirs(OUTPUT_DIR_REPORTS, exist_ok=True)

START_YEAR = 2000
END_YEAR = 2025


# ── Shared ────────────────────────────────────────────────────────────────────

def load_multiband(path: str):
    print(f"Loading: {path}")
    with rasterio.open(path) as src:
        print(f"  Bands: {src.count}  Shape: {src.height}×{src.width}  CRS: {src.crs}")
        data = src.read().astype(float)
        nodata = src.nodata
        if nodata is not None:
            data[data == nodata] = np.nan
        cols_idx, rows_idx = np.meshgrid(np.arange(src.width), np.arange(src.height))
        xs, ys = rasterio.transform.xy(src.transform, rows_idx.flatten(), cols_idx.flatten())
        lons = np.array(xs)
        lats = np.array(ys)
    return data, lats, lons


# ── Annual pipeline ───────────────────────────────────────────────────────────

def export_annual_csv(data, lats, lons):
    n_bands = data.shape[0]
    years = list(range(START_YEAR, START_YEAR + n_bands))

    df = pd.DataFrame({"latitude": lats.round(4), "longitude": lons.round(4)})
    for i, year in enumerate(years):
        df[f"y{year}"] = data[i].flatten()

    year_cols = [f"y{y}" for y in years]
    df["_sum"] = df[year_cols].fillna(0).sum(axis=1)
    df = df[df["_sum"] > 0].drop(columns=["_sum"])

    out = os.path.join(OUTPUT_DIR_DATA, "fire_by_year.csv")
    df.to_csv(out, index=False)
    print(f"\nCSV: {out}  ({len(df):,} pixels with ≥1 fire)")
    print(f"Columns: latitude, longitude, y{years[0]}…y{years[-1]}")
    return df, years


def print_annual_summary(df, years):
    year_cols = [f"y{y}" for y in years]
    total = df[year_cols].fillna(0).sum(axis=1)
    print("\n=== SUMMARY ===")
    for threshold in [1, 5, 10, 15, 20, len(years)]:
        if threshold > len(years):
            continue
        n = (total >= threshold).sum()
        bar = "█" * min(int(n / 200), 40)
        print(f"  Burned {threshold:2d}+ year(s): {n:6,}  {bar}")
    df2 = df.copy()
    df2["total"] = total
    print(f"\nTop 10 most-recurring pixels:")
    print(df2.nlargest(10, "total")[["latitude", "longitude", "total"]].to_string(index=False))


def generate_recurrence_png(df, years, dpi=150):
    year_cols = [f"y{y}" for y in years]
    total = df[year_cols].fillna(0).sum(axis=1)
    max_val = max(total.max(), 1)

    fig, ax = plt.subplots(figsize=(13, 11), facecolor="#0d0d0d")
    ax.set_facecolor("#0d0d0d")
    cmap = mcolors.LinearSegmentedColormap.from_list(
        "burn", ["#ffcc00", "#ff6600", "#cc0000", "#660000"], N=256
    )
    norm = mcolors.Normalize(vmin=1, vmax=max_val)
    sc = ax.scatter(df["longitude"], df["latitude"], c=total, cmap=cmap, norm=norm,
                    s=4, alpha=0.7, linewidths=0)
    ax.plot(98.9853, 18.7883, "w*", markersize=14, zorder=5)
    ax.annotate("Chiang Mai", xy=(98.9853, 18.7883), xytext=(99.1, 18.65),
                color="white", fontsize=9, arrowprops=dict(arrowstyle="->", color="white", lw=0.8))
    cbar = fig.colorbar(sc, ax=ax, fraction=0.03, pad=0.02)
    cbar.set_label("Years burned 2000–2025", color="white", fontsize=9)
    cbar.ax.yaxis.set_tick_params(color="white")
    plt.setp(cbar.ax.yaxis.get_ticklabels(), color="white")
    ax.set_xlim([98.1, 99.6]); ax.set_ylim([17.9, 20.1])
    ax.tick_params(colors="gray", labelsize=8)
    for spine in ax.spines.values():
        spine.set_edgecolor("#333")
    ax.grid(color="#1a1a1a", linewidth=0.4)
    fig.text(0.5, 0.96, "Burn Recurrence: Chiang Mai 2000–2025 | NASA FIRMS MODIS 1km",
             ha="center", color="white", fontsize=14, fontweight="bold")
    fig.text(0.5, 0.925, "github.com/ChiangFai/ChiangFai",
             ha="center", color="#666", fontsize=9)
    out = os.path.join(OUTPUT_DIR_REPORTS, "recurrence_map.png")
    plt.savefig(out, dpi=dpi, bbox_inches="tight", facecolor=fig.get_facecolor())
    plt.close()
    print(f"PNG: {out}")


# ── Weekly pipeline ───────────────────────────────────────────────────────────

def export_weekly_csv(path: str):
    """
    Convert a weekly-season TIF (bands w06…w20) to rows in data/fire_by_week.csv.
    Columns: latitude, longitude, year, week
    Infers the year from the filename: ..._fire_weekly_YYYY_FIRMS.tif
    """
    # Infer year from filename
    match = re.search(r"_weekly_(\d{4})_", os.path.basename(path))
    if not match:
        print("ERROR: cannot infer year from filename.")
        print("Filename must contain '_weekly_YYYY_' (e.g. ChiangMai_fire_weekly_2024_FIRMS.tif)")
        sys.exit(1)
    year = int(match.group(1))

    data, lats, lons = load_multiband(path)
    n_bands = data.shape[0]

    # Band names are w06, w07, … inferred from band count starting at SEASON_START_WEEK=6
    start_week = 6
    rows = []
    for i in range(n_bands):
        week = start_week + i
        band = data[i].flatten()
        mask = np.nan_to_num(band, nan=0.0) > 0
        if mask.sum() == 0:
            continue
        week_lats = lats[mask].round(4)
        week_lons = lons[mask].round(4)
        week_df = pd.DataFrame({
            "latitude": week_lats,
            "longitude": week_lons,
            "year": year,
            "week": week,
        })
        rows.append(week_df)
        print(f"  Week {week:02d}: {mask.sum():,} fire pixels")

    if not rows:
        print("No fire pixels found in any week — check the TIF.")
        return

    new_data = pd.concat(rows, ignore_index=True)
    out = os.path.join(OUTPUT_DIR_DATA, "fire_by_week.csv")

    # Merge with existing data (accumulate multiple years)
    if os.path.exists(out):
        existing = pd.read_csv(out)
        existing = existing[existing["year"] != year]  # replace this year if re-running
        combined = pd.concat([existing, new_data], ignore_index=True)
    else:
        combined = new_data

    combined = combined.sort_values(["year", "week", "latitude", "longitude"])
    combined.to_csv(out, index=False)
    years_in_file = sorted(combined["year"].unique())
    print(f"\nCSV: {out}  ({len(new_data):,} new rows for {year})")
    print(f"Years in file: {years_in_file}")
    print(f"Total rows: {len(combined):,}")


# ── Entry point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Convert GEE fire TIF → CSV")
    parser.add_argument("tif", help="Path to the GeoTIFF exported from GEE")
    parser.add_argument("--weekly", action="store_true",
                        help="Process a weekly-season TIF instead of the annual stack")
    args = parser.parse_args()

    if not os.path.exists(args.tif):
        print(f"File not found: {args.tif}")
        sys.exit(1)

    if args.weekly:
        export_weekly_csv(args.tif)
        print("\nDone. Next:")
        print("  git add data/fire_by_week.csv")
        print("  git commit -m 'Add weekly fire data'")
        print("  git push")
    else:
        data, lats, lons = load_multiband(args.tif)
        df, years = export_annual_csv(data, lats, lons)
        print_annual_summary(df, years)
        generate_recurrence_png(df, years)
        print("\nDone. Next:")
        print("  git add data/fire_by_year.csv reports/recurrence_map.png")
        print("  git commit -m 'Add per-year fire data 2000-2025'")
        print("  git push")
