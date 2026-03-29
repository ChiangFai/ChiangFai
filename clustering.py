"""
DBSCAN spatial clustering on FIRMS fire points.
Detects spatially coordinated ignition events (ring patterns, simultaneous multi-point).
"""

import pandas as pd
import numpy as np
from sklearn.cluster import DBSCAN
from sklearn.preprocessing import StandardScaler
import folium
import os


def cluster_fires(df: pd.DataFrame, eps_km: float = 5.0, min_samples: int = 5) -> pd.DataFrame:
    """
    Run DBSCAN on lat/lon coordinates.
    eps_km: neighborhood radius in km (approx: degrees * 111)
    min_samples: minimum points to form a cluster core
    """
    if df.empty:
        return df

    coords = df[["latitude", "longitude"]].values
    # Convert km to degrees (rough equatorial approximation)
    eps_deg = eps_km / 111.0

    db = DBSCAN(eps=eps_deg, min_samples=min_samples, metric="haversine",
                algorithm="ball_tree")
    # haversine expects radians
    coords_rad = np.radians(coords)
    labels = db.fit_predict(coords_rad)

    df = df.copy()
    df["cluster"] = labels
    n_clusters = len(set(labels)) - (1 if -1 in labels else 0)
    n_noise = (labels == -1).sum()
    print(f"Clusters found: {n_clusters} | Noise points: {n_noise}")
    return df


def flag_simultaneous(df: pd.DataFrame, window_hours: int = 2) -> pd.DataFrame:
    """
    Within each spatial cluster, flag if multiple ignitions occurred within window_hours.
    Simultaneous + spatially dispersed = coordinated-burn signature.
    """
    if "acq_datetime" not in df.columns or "cluster" not in df.columns:
        return df

    flagged = []
    for cluster_id, group in df[df["cluster"] >= 0].groupby("cluster"):
        time_range = (group["acq_datetime"].max() - group["acq_datetime"].min()).total_seconds() / 3600
        if time_range <= window_hours and len(group) >= 3:
            group = group.copy()
            group["coordinated_flag"] = True
            flagged.append(group)

    if flagged:
        flagged_df = pd.concat(flagged)
        print(f"Coordinated ignition clusters flagged: {flagged_df['cluster'].nunique()}")
        return df.merge(flagged_df[["cluster", "coordinated_flag"]].drop_duplicates(),
                        on="cluster", how="left")
    df["coordinated_flag"] = False
    return df


def map_clusters(df: pd.DataFrame, output_path: str = "reports/clusters_map.html"):
    """Save a Folium map with cluster colors."""
    if df.empty:
        return

    center = [df["latitude"].mean(), df["longitude"].mean()]
    m = folium.Map(location=center, zoom_start=9)

    colors = ["red", "blue", "green", "purple", "orange", "darkred",
              "lightred", "beige", "darkblue", "darkgreen", "cadetblue"]

    for _, row in df.iterrows():
        cluster_id = int(row.get("cluster", -1))
        color = colors[cluster_id % len(colors)] if cluster_id >= 0 else "gray"
        coordinated = row.get("coordinated_flag", False)
        icon = "fire" if coordinated else "info-sign"
        folium.CircleMarker(
            location=[row["latitude"], row["longitude"]],
            radius=5,
            color=color,
            fill=True,
            fill_opacity=0.7,
            popup=f"Cluster {cluster_id} | FRP: {row.get('frp', 'N/A')} | {row.get('acq_datetime', '')}",
        ).add_to(m)

    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    m.save(output_path)
    print(f"Cluster map saved: {output_path}")


if __name__ == "__main__":
    # Example: load a saved FIRMS snapshot and cluster it
    import glob
    snapshots = sorted(glob.glob("data/firms_snapshot_*.csv"))
    if not snapshots:
        print("No snapshot files found. Run real_time_alerts.py first.")
    else:
        df = pd.read_csv(snapshots[-1], parse_dates=["acq_datetime"])
        df = cluster_fires(df, eps_km=5.0, min_samples=3)
        df = flag_simultaneous(df, window_hours=3)
        map_clusters(df)
        df.to_csv("reports/clustered_fires.csv", index=False)
        print("Saved: reports/clustered_fires.csv")
