"""
Streamlit dashboard for Chiang Mai fire forensics.
Run: streamlit run dashboard/app.py
"""

import streamlit as st
import pandas as pd
import folium
from streamlit_folium import st_folium
import glob
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

st.set_page_config(page_title="Chiang Mai Fire Forensics", layout="wide")
st.title("Open Spatial Analysis of Agricultural Burning Patterns")
st.caption("Northern Thailand · 2018–2026 · Data: NASA FIRMS, Copernicus Sentinel-2 via GEE")

# --- Sidebar ---
st.sidebar.header("Controls")
days_back = st.sidebar.slider("FIRMS lookback (days)", 1, 10, 1)
eps_km = st.sidebar.slider("Cluster radius (km)", 1.0, 20.0, 5.0)
min_pts = st.sidebar.slider("Min cluster size", 2, 20, 3)

# --- Load latest snapshot ---
snapshots = sorted(glob.glob("data/firms_snapshot_*.csv"))

if snapshots:
    df = pd.read_csv(snapshots[-1])
    if "acq_datetime" in df.columns:
        df["acq_datetime"] = pd.to_datetime(df["acq_datetime"])

    st.subheader(f"Latest snapshot: `{os.path.basename(snapshots[-1])}`")
    col1, col2, col3 = st.columns(3)
    col1.metric("Total detections", len(df))
    if "frp" in df.columns:
        col2.metric("Avg FRP (MW)", f"{df['frp'].mean():.1f}")
        col3.metric("Max FRP (MW)", f"{df['frp'].max():.1f}")

    # Map
    st.subheader("Fire detections map")
    m = folium.Map(location=[18.8, 98.9], zoom_start=9)
    for _, row in df.iterrows():
        folium.CircleMarker(
            location=[row["latitude"], row["longitude"]],
            radius=4,
            color="red",
            fill=True,
            fill_opacity=0.6,
            popup=str(row.get("acq_datetime", "")),
        ).add_to(m)
    st_folium(m, width=900, height=500)

    # Raw data table
    with st.expander("Raw data"):
        st.dataframe(df)
else:
    st.warning("No FIRMS snapshots found. Run `real_time_alerts.py` first to fetch data.")

# --- Recurrence map (if GEE export complete) ---
recurrence_html = "reports/chiang_mai_burn_map.html"
if os.path.exists(recurrence_html):
    st.subheader("Burn recurrence map (Sentinel-2 dNBR)")
    with open(recurrence_html, "r") as f:
        st.components.v1.html(f.read(), height=500)
else:
    st.info("Burn recurrence map not yet generated. Run `retrospective_analysis.py` and export from GEE.")
