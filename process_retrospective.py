"""
Convert GEE fire TIFs → CSVs for the Streamlit app.

Annual (default — finds TIF in Downloads automatically):
  python process_retrospective.py
  python process_retrospective.py --tif "C:/path/to/file.tif"

Weekly all-years (finds TIF in Downloads automatically):
  python process_retrospective.py --weekly-all
  python process_retrospective.py --weekly-all --tif "C:/path/to/file.tif"

Weekly single year (merge into existing fire_by_week.csv):
  python process_retrospective.py --weekly-single
  python process_retrospective.py --weekly-single --tif "C:/path/to/file.tif"
"""

import argparse
import datetime
import glob
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

SEASON_START_WEEK = 6
SEASON_END_WEEK = 20


# ── Auto-find TIF ─────────────────────────────────────────────────────────────

def find_tif(pattern: str) -> str:
    """
    Search common download locations for a TIF matching pattern.
    Returns the most recently modified match.
    """
    search_dirs = [
        os.path.expanduser("~/Downloads"),
        os.path.expanduser("~/Desktop"),
        os.path.expanduser("~/OneDrive/Downloads"),
        os.path.expanduser("~/OneDrive/Desktop"),
        os.getcwd(),
    ]
    candidates = []
    for d in search_dirs:
        if os.path.isdir(d):
            candidates.extend(glob.glob(os.path.join(d, pattern)))
            candidates.extend(glob.glob(os.path.join(d, "**", pattern), recursive=True))

    if not candidates:
        return ""

    candidates = sorted(set(candidates), key=os.path.getmtime, reverse=True)
    return candidates[0]


def resolve_tif(arg_tif: str, pattern: str, description: str) -> str:
    if arg_tif:
        if not os.path.exists(arg_tif):
            print(f"ERROR: File not found: {arg_tif}")
            sys.exit(1)
        return arg_tif

    print(f"No --tif given. Searching Downloads and Desktop for {description}...")
    path = find_tif(pattern)
    if not path:
        print(f"ERROR: Could not find {description}.")
        print(f"  Looked for: {pattern}")
        print(f"  Pass the path explicitly: --tif \"C:/Users/Monpaga/Downloads/yourfile.tif\"")
        sys.exit(1)

    print(f"  Found: {path}")
    return path


# ── Shared loader ─────────────────────────────────────────────────────────────

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
    return data, np.array(ys), np.array(xs)


# ── Annual pipeline ───────────────────────────────────────────────────────────

def process_annual(path: str):
    data, lats, lons = load_multiband(path)
    n_bands = data.shape[0]
    years = list(range(2000, 2000 + n_bands))

    df = pd.DataFrame({"latitude": lats.round(4), "longitude": lons.round(4)})
    for i, year in enumerate(years):
        df[f"y{year}"] = data[i].flatten()

    year_cols = [f"y{y}" for y in years]
    df["_sum"] = df[year_cols].fillna(0).sum(axis=1)
    df = df[df["_sum"] > 0].drop(columns=["_sum"])

    out = os.path.join(OUTPUT_DIR_DATA, "fire_by_year.csv")
    df.to_csv(out, index=False)
    print(f"\n→ {out}  ({len(df):,} pixels with ≥1 fire)")

    _print_annual_summary(df, years)
    _generate_recurrence_png(df, years)

    print("\nNext:")
    print("  git add data/fire_by_year.csv reports/recurrence_map.png")
    print("  git commit -m 'Add per-year fire data 2000-2025' && git push")


def _print_annual_summary(df, years):
    year_cols = [f"y{y}" for y in years]
    total = df[year_cols].fillna(0).sum(axis=1)
    print("\n=== RECURRENCE SUMMARY ===")
    for t in [1, 5, 10, 15, 20, len(years)]:
        if t > len(years):
            continue
        n = (total >= t).sum()
        print(f"  Burned {t:2d}+ year(s): {n:6,}  {'█' * min(int(n / 200), 40)}")


def _generate_recurrence_png(df, years, dpi=150):
    year_cols = [f"y{y}" for y in years]
    total = df[year_cols].fillna(0).sum(axis=1)
    max_val = max(total.max(), 1)
    cmap = mcolors.LinearSegmentedColormap.from_list(
        "burn", ["#ffcc00", "#ff6600", "#cc0000", "#660000"], N=256
    )
    fig, ax = plt.subplots(figsize=(13, 11), facecolor="#0d0d0d")
    ax.set_facecolor("#0d0d0d")
    sc = ax.scatter(df["longitude"], df["latitude"], c=total,
                    cmap=cmap, norm=mcolors.Normalize(vmin=1, vmax=max_val),
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
    print(f"→ {out}")


# ── Weekly pipeline ───────────────────────────────────────────────────────────

def _parse_weekly_band_name(name):
    """Parse 'y2000w06' → (2000, 6). Returns None if no match."""
    m = re.match(r"y(\d{4})w(\d{2})", str(name))
    if m:
        return int(m.group(1)), int(m.group(2))
    return None


def process_weekly_all(path: str):
    """
    All-years weekly TIF (390 bands: y2000w06 … y2025w20).
    Produces data/fire_by_week.csv with columns: latitude, longitude, year, week
    """
    data, lats, lons = load_multiband(path)
    n_bands = data.shape[0]

    # Band order matches export: year outer loop, week inner loop
    years_weeks = [
        (year, week)
        for year in range(2000, 2000 + (n_bands // (SEASON_END_WEEK - SEASON_START_WEEK + 1)))
        for week in range(SEASON_START_WEEK, SEASON_END_WEEK + 1)
    ]
    if len(years_weeks) != n_bands:
        # Fallback: infer from band count alone
        years_weeks = []
        for i in range(n_bands):
            year_offset = i // (SEASON_END_WEEK - SEASON_START_WEEK + 1)
            week_offset = i % (SEASON_END_WEEK - SEASON_START_WEEK + 1)
            years_weeks.append((2000 + year_offset, SEASON_START_WEEK + week_offset))

    rows = []
    for i, (year, week) in enumerate(years_weeks):
        band = np.nan_to_num(data[i].flatten(), nan=0.0)
        mask = band > 0
        if mask.sum() == 0:
            continue
        rows.append(pd.DataFrame({
            "latitude":  lats[mask].round(4),
            "longitude": lons[mask].round(4),
            "year": year,
            "week": week,
        }))

    if not rows:
        print("No fire pixels found — check the TIF.")
        sys.exit(1)

    df = pd.concat(rows, ignore_index=True)
    df = df.sort_values(["year", "week", "latitude", "longitude"])

    out = os.path.join(OUTPUT_DIR_DATA, "fire_by_week.csv")
    df.to_csv(out, index=False)
    years_in = sorted(df["year"].unique())
    print(f"\n→ {out}")
    print(f"  {len(df):,} fire pixel-weeks across years {years_in[0]}–{years_in[-1]}")
    print(f"  Years: {years_in}")
    print("\nNext:")
    print("  git add data/fire_by_week.csv")
    print("  git commit -m 'Add weekly fire data all years' && git push")


def process_weekly_single(path: str):
    """
    Single-year weekly TIF — merges into existing fire_by_week.csv.
    Infers year from filename: *_weekly_YYYY_*.tif
    """
    m = re.search(r"_weekly_(\d{4})_", os.path.basename(path))
    if not m:
        print("ERROR: Cannot infer year from filename.")
        print("Expected filename pattern: ChiangMai_fire_weekly_YYYY_FIRMS.tif")
        sys.exit(1)
    year = int(m.group(1))

    data, lats, lons = load_multiband(path)
    rows = []
    for i in range(data.shape[0]):
        week = SEASON_START_WEEK + i
        band = np.nan_to_num(data[i].flatten(), nan=0.0)
        mask = band > 0
        if mask.sum() == 0:
            continue
        rows.append(pd.DataFrame({
            "latitude":  lats[mask].round(4),
            "longitude": lons[mask].round(4),
            "year": year,
            "week": week,
        }))
        print(f"  Week {week:02d}: {mask.sum():,} fire pixels")

    if not rows:
        print("No fire pixels found.")
        return

    new_data = pd.concat(rows, ignore_index=True)
    out = os.path.join(OUTPUT_DIR_DATA, "fire_by_week.csv")
    if os.path.exists(out):
        existing = pd.read_csv(out)
        existing = existing[existing["year"] != year]
        combined = pd.concat([existing, new_data], ignore_index=True)
    else:
        combined = new_data

    combined = combined.sort_values(["year", "week", "latitude", "longitude"])
    combined.to_csv(out, index=False)
    print(f"\n→ {out}  ({len(new_data):,} rows for {year})")
    print(f"  Years in file: {sorted(combined['year'].unique())}")


# ── Entry point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Convert GEE fire TIF → CSV for ChiangFai app",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python process_retrospective.py                          # annual, auto-find TIF
  python process_retrospective.py --tif path/to/file.tif  # annual, explicit path
  python process_retrospective.py --weekly-all             # all years weekly, auto-find
  python process_retrospective.py --weekly-single          # one year weekly, auto-find
""",
    )
    parser.add_argument("--tif", default="",
                        help="Path to TIF file. If omitted, searches Downloads and Desktop automatically.")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--weekly-all", action="store_true",
                      help="Process all-years weekly TIF (ChiangMai_fire_weekly_all_years_FIRMS.tif)")
    mode.add_argument("--weekly-single", action="store_true",
                      help="Process single-year weekly TIF, merge into fire_by_week.csv")
    args = parser.parse_args()

    if args.weekly_all:
        tif = resolve_tif(args.tif, "*fire_weekly_all_years*.tif",
                          "ChiangMai_fire_weekly_all_years_FIRMS.tif")
        process_weekly_all(tif)

    elif args.weekly_single:
        tif = resolve_tif(args.tif, "*fire_weekly_*_FIRMS.tif",
                          "ChiangMai_fire_weekly_YYYY_FIRMS.tif")
        process_weekly_single(tif)

    else:
        tif = resolve_tif(args.tif, "*fire_by_year*.tif",
                          "ChiangMai_fire_by_year_2000_2025_FIRMS.tif")
        process_annual(tif)
