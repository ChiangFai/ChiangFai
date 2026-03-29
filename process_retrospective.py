"""
Processes the GEE-exported burn recurrence GeoTIFF into shareable formats.

Run after your Google Drive export lands:
  python process_retrospective.py path/to/Chiang_Mai_burn_recurrence_2018_2026.tif

Outputs:
  data/burn_recurrence.csv       — lightweight grid of burn counts (committable to GitHub)
  reports/recurrence_map.png     — publication-quality heatmap (committable)
  reports/recurrence_map_hi.png  — high-res version for print/media
"""

import sys
import os
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.colors as mcolors
from datetime import datetime

try:
    import rasterio
    from rasterio.enums import Resampling
    from rasterio.warp import transform_bounds
except ImportError:
    print("Run: pip install rasterio")
    sys.exit(1)

OUTPUT_DIR_DATA = "data"
OUTPUT_DIR_REPORTS = "reports"
os.makedirs(OUTPUT_DIR_DATA, exist_ok=True)
os.makedirs(OUTPUT_DIR_REPORTS, exist_ok=True)

YEARS = 8  # 2018–2025 inclusive (adjust if export covers more)


def load_geotiff(path: str):
    print(f"Loading: {path}")
    with rasterio.open(path) as src:
        print(f"  CRS: {src.crs}")
        print(f"  Shape: {src.height} x {src.width} px")
        print(f"  Bounds: {src.bounds}")
        print(f"  Bands: {src.count}")

        data = src.read(1).astype(float)
        nodata = src.nodata
        if nodata is not None:
            data[data == nodata] = np.nan

        transform = src.transform
        height, width = data.shape

        # Build lat/lon arrays
        cols, rows = np.meshgrid(np.arange(width), np.arange(height))
        xs, ys = rasterio.transform.xy(transform, rows.flatten(), cols.flatten())
        lons = np.array(xs)
        lats = np.array(ys)
        values = data.flatten()

    return lats, lons, values, data, src.transform, src.crs


def export_csv(lats, lons, values, downsample_factor: int = 5):
    """
    Downsamples and exports non-zero burn pixels to CSV.
    downsample_factor=5 at 10m → ~50m effective resolution; keeps file small enough for GitHub.
    """
    mask = ~np.isnan(values) & (values > 0)
    df = pd.DataFrame({
        "latitude": lats[mask],
        "longitude": lons[mask],
        "burn_count": values[mask].astype(int),
    })

    # Spatial downsampling via rounding to ~0.0005 deg (~50m) grid
    precision = 4 - int(np.log10(downsample_factor))
    df["latitude"] = df["latitude"].round(precision)
    df["longitude"] = df["longitude"].round(precision)
    df = df.groupby(["latitude", "longitude"])["burn_count"].max().reset_index()

    out = os.path.join(OUTPUT_DIR_DATA, "burn_recurrence.csv")
    df.to_csv(out, index=False)
    print(f"\nCSV: {out}  ({len(df):,} non-zero pixels)")
    print(f"  Pixels burned 1+ years: {(df['burn_count'] >= 1).sum():,}")
    print(f"  Pixels burned 3+ years: {(df['burn_count'] >= 3).sum():,}")
    print(f"  Pixels burned 5+ years: {(df['burn_count'] >= 5).sum():,}")
    print(f"  Pixels burned every year ({YEARS}): {(df['burn_count'] >= YEARS).sum():,}")
    return df


def generate_png(data: np.ndarray, transform, title_suffix: str = "", dpi: int = 150):
    """Renders a dark-theme recurrence heatmap PNG."""
    fig, ax = plt.subplots(figsize=(13, 11), facecolor="#0d0d0d")
    ax.set_facecolor("#0d0d0d")

    # Custom colormap: black → yellow → orange → red → deep red
    colors_list = ["#0d0d0d", "#1a1a00", "#ffcc00", "#ff6600", "#cc0000", "#660000"]
    cmap = mcolors.LinearSegmentedColormap.from_list("burn", colors_list, N=YEARS + 1)
    norm = mcolors.BoundaryNorm(boundaries=range(0, YEARS + 2), ncolors=YEARS + 1)

    # Mask zeros so unburned pixels stay black (background)
    masked = np.ma.masked_where(np.isnan(data) | (data == 0), data)

    height, width = data.shape
    xs_min = transform.c
    xs_max = transform.c + transform.a * width
    ys_max = transform.f
    ys_min = transform.f + transform.e * height
    extent = [xs_min, xs_max, ys_min, ys_max]

    im = ax.imshow(masked, cmap=cmap, norm=norm, extent=extent,
                   aspect="auto", interpolation="nearest", zorder=2)

    # Chiang Mai city
    ax.plot(98.9853, 18.7883, "w*", markersize=14, zorder=5)
    ax.annotate("เชียงใหม่\nChiang Mai", xy=(98.9853, 18.7883),
                xytext=(99.1, 18.65), color="white", fontsize=9, zorder=6,
                arrowprops=dict(arrowstyle="->", color="white", lw=0.8))

    ax.grid(color="#1a1a1a", linewidth=0.4, zorder=0)
    ax.tick_params(colors="gray", labelsize=8)
    for spine in ax.spines.values():
        spine.set_edgecolor("#333333")

    # Colorbar
    cbar = fig.colorbar(im, ax=ax, fraction=0.03, pad=0.02, ticks=range(0, YEARS + 1))
    cbar.set_label("จำนวนปีที่เกิดไฟ / Years burned (2018–2025)", color="white", fontsize=9)
    cbar.ax.yaxis.set_tick_params(color="white")
    plt.setp(cbar.ax.yaxis.get_ticklabels(), color="white")

    fig.text(0.5, 0.96,
             "พื้นที่เกิดไฟซ้ำ จังหวัดเชียงใหม่  |  Burn Recurrence: Chiang Mai 2018–2025",
             ha="center", color="white", fontsize=15, fontweight="bold")
    fig.text(0.5, 0.925,
             "Sentinel-2 dNBR · 10m resolution · Google Earth Engine · github.com/ChiangFai/ChiangFai",
             ha="center", color="#888888", fontsize=9)

    slug = f"_hi" if dpi >= 300 else ""
    out = os.path.join(OUTPUT_DIR_REPORTS, f"recurrence_map{slug}.png")
    plt.savefig(out, dpi=dpi, bbox_inches="tight", facecolor=fig.get_facecolor())
    plt.close()
    print(f"PNG ({dpi}dpi): {out}")
    return out


def print_summary(df: pd.DataFrame):
    print("\n=== RETROSPECTIVE SUMMARY ===")
    for y in range(1, YEARS + 1):
        n = (df["burn_count"] >= y).sum()
        bar = "█" * min(int(n / 500), 40)
        print(f"  Burned {y:2d}+ year(s): {n:6,}  {bar}")
    top = df.nlargest(10, "burn_count")[["latitude", "longitude", "burn_count"]]
    print("\nTop 10 most-recurring burn pixels:")
    print(top.to_string(index=False))


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python process_retrospective.py <path_to_geotiff>")
        print("Example: python process_retrospective.py ~/Downloads/Chiang_Mai_burn_recurrence_2018_2026.tif")
        sys.exit(1)

    tif_path = sys.argv[1]
    if not os.path.exists(tif_path):
        print(f"File not found: {tif_path}")
        sys.exit(1)

    lats, lons, values, data, transform, crs = load_geotiff(tif_path)
    df = export_csv(lats, lons, values)
    generate_png(data, transform, dpi=150)
    generate_png(data, transform, dpi=300)
    print_summary(df)

    print("\nDone. Next:")
    print("  git add data/burn_recurrence.csv reports/recurrence_map.png")
    print("  git commit -m 'Add 8-year burn recurrence data'")
    print("  git push")
    print("\nThen upload the raw .tif to GitHub Releases for full data access.")
