"""
Processes the GEE multi-band fire-by-year GeoTIFF into a CSV.

Run after your Google Drive export lands:
  python process_retrospective.py "C:/Users/.../Chiang Mai_fire_by_year_2000_2025_FIRMS.tif"

Output:
  data/fire_by_year.csv   — columns: latitude, longitude, y2000, y2001, ..., y2025
  reports/recurrence_map.png   — 26-year total recurrence heatmap
"""

import sys
import os
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


def load_multiband(path: str):
    print(f"Loading: {path}")
    with rasterio.open(path) as src:
        print(f"  Bands: {src.count}  Shape: {src.height}x{src.width}  CRS: {src.crs}")
        data = src.read().astype(float)  # shape: (bands, height, width)
        nodata = src.nodata
        if nodata is not None:
            data[data == nodata] = np.nan
        transform = src.transform
        height, width = src.height, src.width
        cols, rows = np.meshgrid(np.arange(width), np.arange(height))
        xs, ys = rasterio.transform.xy(transform, rows.flatten(), cols.flatten())
        lons = np.array(xs)
        lats = np.array(ys)
    return data, lats, lons, transform


def export_csv(data, lats, lons):
    n_bands = data.shape[0]
    years = list(range(START_YEAR, START_YEAR + n_bands))

    df = pd.DataFrame({"latitude": lats, "longitude": lons})
    for i, year in enumerate(years):
        df[f"y{year}"] = data[i].flatten()

    # Drop rows where all year values are 0 or NaN (unburned)
    year_cols = [f"y{y}" for y in years]
    df["burn_count"] = df[year_cols].sum(axis=1)
    df = df[df["burn_count"] > 0].drop(columns=["burn_count"])

    # Round coordinates to reduce file size
    df["latitude"] = df["latitude"].round(4)
    df["longitude"] = df["longitude"].round(4)

    out = os.path.join(OUTPUT_DIR_DATA, "fire_by_year.csv")
    df.to_csv(out, index=False)
    print(f"\nCSV: {out}  ({len(df):,} pixels with at least one fire)")
    print(f"Columns: latitude, longitude, y{years[0]}…y{years[-1]}")
    return df, years


def print_summary(df, years):
    year_cols = [f"y{y}" for y in years]
    total = df[year_cols].sum(axis=1)
    print("\n=== SUMMARY ===")
    for threshold in [1, 5, 10, 15, 20, len(years)]:
        if threshold > len(years):
            continue
        n = (total >= threshold).sum()
        bar = "█" * min(int(n / 200), 40)
        print(f"  Burned {threshold:2d}+ year(s): {n:6,}  {bar}")
    print(f"\nTop 10 most-recurring pixels:")
    df2 = df.copy()
    df2["total"] = total
    print(df2.nlargest(10, "total")[["latitude", "longitude", "total"]].to_string(index=False))


def generate_png(df, years, dpi=150):
    year_cols = [f"y{y}" for y in years]
    total = df[year_cols].sum(axis=1)
    max_val = total.max()

    fig, ax = plt.subplots(figsize=(13, 11), facecolor="#0d0d0d")
    ax.set_facecolor("#0d0d0d")
    norm = mcolors.Normalize(vmin=1, vmax=max_val)
    cmap = mcolors.LinearSegmentedColormap.from_list(
        "burn", ["#ffcc00", "#ff6600", "#cc0000", "#660000"], N=256
    )
    sc = ax.scatter(df["longitude"], df["latitude"], c=total, cmap=cmap, norm=norm,
                    s=4, alpha=0.7, linewidths=0)
    ax.plot(98.9853, 18.7883, "w*", markersize=14, zorder=5)
    ax.annotate("Chiang Mai", xy=(98.9853, 18.7883), xytext=(99.1, 18.65),
                color="white", fontsize=9, arrowprops=dict(arrowstyle="->", color="white", lw=0.8))
    cbar = fig.colorbar(sc, ax=ax, fraction=0.03, pad=0.02)
    cbar.set_label("Years burned 2000-2025", color="white", fontsize=9)
    cbar.ax.yaxis.set_tick_params(color="white")
    plt.setp(cbar.ax.yaxis.get_ticklabels(), color="white")
    ax.set_xlim([98.1, 99.6]); ax.set_ylim([17.9, 20.1])
    ax.tick_params(colors="gray", labelsize=8)
    for spine in ax.spines.values(): spine.set_edgecolor("#333")
    ax.grid(color="#1a1a1a", linewidth=0.4)
    fig.text(0.5, 0.96, "Burn Recurrence: Chiang Mai 2000-2025 | NASA FIRMS MODIS 1km",
             ha="center", color="white", fontsize=14, fontweight="bold")
    fig.text(0.5, 0.925, "github.com/ChiangFai/ChiangFai",
             ha="center", color="#666", fontsize=9)
    out = os.path.join(OUTPUT_DIR_REPORTS, "recurrence_map.png")
    plt.savefig(out, dpi=dpi, bbox_inches="tight", facecolor=fig.get_facecolor())
    plt.close()
    print(f"PNG: {out}")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python process_retrospective.py <path_to_tif>")
        sys.exit(1)
    path = sys.argv[1]
    if not os.path.exists(path):
        print(f"File not found: {path}")
        sys.exit(1)
    data, lats, lons, transform = load_multiband(path)
    df, years = export_csv(data, lats, lons)
    print_summary(df, years)
    generate_png(df, years)
    print("\nDone. Next:")
    print("  git add data/fire_by_year.csv reports/recurrence_map.png")
    print("  git commit -m 'Add per-year fire data 2000-2025'")
    print("  git push")
