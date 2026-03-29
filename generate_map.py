"""
Generates a publication-quality PNG heatmap of fire detections.
Shareable on Facebook, Twitter, LINE, etc.
Run: python generate_map.py
Output: reports/fire_map_YYYYMMDD.png
"""

import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.colors as mcolors
import numpy as np
import glob
import os
from datetime import datetime

OUTPUT_DIR = "reports"
os.makedirs(OUTPUT_DIR, exist_ok=True)


def load_latest_snapshot() -> pd.DataFrame:
    snapshots = sorted(glob.glob("data/firms_snapshot_*.csv"))
    if not snapshots:
        raise FileNotFoundError("No FIRMS snapshots found. Run real_time_alerts.py first.")
    path = snapshots[-1]
    print(f"Loading: {path}")
    return pd.read_csv(path)


def generate_heatmap(df: pd.DataFrame):
    date_str = datetime.utcnow().strftime("%d %B %Y")
    date_file = datetime.utcnow().strftime("%Y%m%d")
    count = len(df)

    fig, ax = plt.subplots(figsize=(12, 10), facecolor="#0d0d0d")
    ax.set_facecolor("#0d0d0d")

    # Normalize FRP for color intensity
    frp = df["frp"].clip(upper=df["frp"].quantile(0.98))
    frp_norm = (frp - frp.min()) / (frp.max() - frp.min() + 1e-9)

    # Background grid lines (subtle)
    ax.grid(color="#1a1a1a", linewidth=0.5, zorder=0)

    # Fire points — glow effect via layered scatter
    cmap = plt.cm.YlOrRd
    for alpha, size_mult in [(0.08, 6), (0.15, 3), (0.6, 1.2), (1.0, 0.5)]:
        ax.scatter(
            df["longitude"], df["latitude"],
            c=frp_norm, cmap=cmap,
            s=frp_norm * 40 * size_mult + 2,
            alpha=alpha, linewidths=0, zorder=2
        )

    # Chiang Mai city marker
    ax.plot(98.9853, 18.7883, "w*", markersize=12, zorder=5, label="Chiang Mai City")
    ax.annotate("เชียงใหม่", xy=(98.9853, 18.7883), xytext=(99.05, 18.72),
                color="white", fontsize=9, zorder=6,
                arrowprops=dict(arrowstyle="->", color="white", lw=0.8))

    # Colorbar
    sm = plt.cm.ScalarMappable(cmap=cmap, norm=mcolors.Normalize(vmin=frp.min(), vmax=frp.max()))
    sm.set_array([])
    cbar = fig.colorbar(sm, ax=ax, fraction=0.03, pad=0.02)
    cbar.set_label("Fire Radiative Power (MW)", color="white", fontsize=9)
    cbar.ax.yaxis.set_tick_params(color="white")
    plt.setp(cbar.ax.yaxis.get_ticklabels(), color="white")

    # Bounds
    ax.set_xlim([97.4, 99.6])
    ax.set_ylim([17.3, 20.6])
    ax.tick_params(colors="gray", labelsize=8)
    for spine in ax.spines.values():
        spine.set_edgecolor("#333333")

    # Titles
    fig.text(0.5, 0.96,
             f"จุดความร้อนในเชียงใหม่  |  Fire Detections: Chiang Mai",
             ha="center", color="white", fontsize=16, fontweight="bold")
    fig.text(0.5, 0.925,
             f"{count:,} detections in last 24 hours  ·  {date_str}  ·  Source: NASA FIRMS VIIRS",
             ha="center", color="#aaaaaa", fontsize=10)
    fig.text(0.5, 0.02,
             "github.com/ChiangFai/ChiangFai  ·  Open data, open methodology",
             ha="center", color="#555555", fontsize=8)

    ax.legend(loc="upper left", facecolor="#1a1a1a", edgecolor="#333333",
              labelcolor="white", fontsize=9)

    out = os.path.join(OUTPUT_DIR, f"fire_map_{date_file}.png")
    plt.savefig(out, dpi=150, bbox_inches="tight", facecolor=fig.get_facecolor())
    plt.close()
    print(f"Saved: {out}")
    return out


if __name__ == "__main__":
    df = load_latest_snapshot()
    path = generate_heatmap(df)
    print(f"\nShare this image. It shows {len(df):,} fire detections in Chiang Mai in 24 hours.")
